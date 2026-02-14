# StartD8 Agent Communication Design

**Status**: Draft (requirements polishing)
**Created**: 2026-02-14
**Companion document**: [ContextCore A2A Communications Design](../../ContextCore/docs/design/contextcore-a2a-comms-design.md) — governs cross-system pipeline boundaries
**Related requirements**: [Artisan Requirements](../ARTISAN_REQUIREMENTS.md) (AR-3xx ContextCore Data Flow), [Architectural Review Requirements](../ARCHITECTURAL_REVIEW_REQUIREMENTS.md) (RV-xxx CRP)

---

## Overview

This document defines how agents communicate within the StartD8 SDK — the internal orchestration patterns, data flow contracts, and handoff mechanisms that operate *inside* the execution layer that ContextCore governs from the outside.

### Relationship to ContextCore A2A

ContextCore and StartD8 serve complementary roles in the same pipeline:

| Concern | ContextCore A2A | StartD8 Agent Communication |
|---------|----------------|-----------------------------|
| **Scope** | Cross-system governance (Init → Export → Ingest → Build → Output) | Intra-SDK agent orchestration (how agents coordinate within a single workflow run) |
| **Interaction model** | Contract-first boundary validation between independent systems | Orchestrator-centric: orchestrators call agents; agents never call each other |
| **Message format** | Typed contracts (TaskSpanContract, HandoffContract, ArtifactIntent, GateResult) | Plain-text prompts/responses + untyped context dicts (formalization in progress) |
| **Quality gates** | 6 pipeline gates with structured GateResult at every handoff boundary | Snippet validation (CRP), review scores (artisan), domain preflight (pre-generation) |
| **Observability** | OTel spans with A2A semantic conventions at pipeline boundaries | OTel spans per phase (AR-6xx), event bus for notifications, cost/token tracking |

> **The boundary**: ContextCore governs Steps 1-3 and 5-7 of the pipeline. StartD8 is the execution engine for Steps 4 and 6. The `integrations/contextcore.py` adapter is the bridge point where ContextCore governance contracts wrap StartD8's internal handoffs.

### Core Principle

> **Agents are stateless functions. Orchestrators own state, sequencing, and inter-agent data flow.**

StartD8 agents do not communicate with each other. They receive a prompt, produce a response, and return. All coordination — context propagation, phase sequencing, retry logic, cost tracking — lives in the orchestration layer.

### Current Status

Phases 1–3 are now implemented. The remaining work is Phase 4 (Cross-System Integration):

- **Phase 1 (Context Contract)** — Pydantic v2 models for per-phase context validation, boundary validation, and handoff schema enforcement
- **Phase 2 (Data Flow Fixes)** — Fixes 1-5 from [`ARTISAN_CONTEXTCORE_DATA_FLOW_FIXES.md`](../plans/ARTISAN_CONTEXTCORE_DATA_FLOW_FIXES.md) implemented: provenance chain, `parameter_sources`, `semantic_conventions`, and `output_conventions` propagation
- **Phase 3 (Ingestion Strengthening)** — Export preflight with source_checksum verification, `preflight-report.json` artifact, `ingestion-traceability.json` with `refine_impact`, Prime YAML requirement enrichment
- **Phase 4 (Cross-System Integration)** — COMPLETED. GateResult contracts emitted from internal quality gates (review, preflight), HandoffData wrapped in HandoffContract, and context checksums added to handoff (closing B-14).
- **Remaining issues**: 10 open from 33 cataloged ([`ARTISAN_WORKFLOW_ISSUES_CATALOG.md`](../ARTISAN_WORKFLOW_ISSUES_CATALOG.md)) — B-15 (no shared schema version) and B-12 (seed schema enforcement advisory-only) remain open.

This document captures the implemented state, the remaining gaps, and the next phase.

---

## Layer 1: Agent Interface Contract

### BaseAgent Protocol

Every agent in StartD8 implements the `BaseAgent` abstract class:

```text
BaseAgent
├── generate(prompt: str) -> GenerateResult          # Sync wrapper
├── agenerate(prompt: str) -> GenerateResult          # Async primary
├── create_response(prompt: str, ...) -> AgentResponse # With cost tracking
└── acreate_response(prompt: str, ...) -> AgentResponse # Async with cost
```

**Input**: Plain-text `prompt` string. No structured message envelope.

**Output**: `GenerateResult` tuple `(text: str, time_ms: int, token_usage: dict)` or `AgentResponse` with metadata.

**Invariants**:
- Agents are stateless — no memory of prior calls (unless the orchestrator re-injects prior context in the prompt)
- Agents never call other agents
- Agents never read or write shared state
- Agent creation goes through `ProviderRegistry.discover()` → `provider.validate_config()` → `provider.create_agent(model)`

### Agent Specification Format

Agents are identified by `provider:model` strings:
- `anthropic:claude-sonnet-4-20250514`
- `openai:gpt-4-turbo-preview`
- `gemini:gemini-2.5-pro`
- `mock:mock-model` (testing)

Resolution: `resolve_agents(["anthropic:claude-sonnet-4-20250514"])` → discovers provider, validates config, creates instance.

### TrackedAgent Observability Wrapper

`TrackedAgentMixin` wraps `agenerate()` in OTel spans without changing the communication interface:

```text
TrackedAgent.agenerate(prompt)
  └── OTel span: agent.call
        ├── attributes: agent_name, model, provider
        ├── events: truncation_detected, truncation_warning
        └── delegates to: super().agenerate(prompt)
```

### Model Tier Architecture (Artisan)

The artisan contractor uses a 3-tier model allocation:

| Role | Default Model | Purpose | Typical Agent Spec |
|------|--------------|---------|-------------------|
| Drafter | Claude Haiku | Fast, cheap generation | `anthropic:claude-haiku-4-5-20251001` |
| Validator | Claude Sonnet | Balanced quality gating | `anthropic:claude-sonnet-4-5-20250929` |
| Reviewer | Claude Opus | Flagship independent review | `anthropic:claude-opus-4-6` |

> **Runtime default**: 2-tier (Haiku + Opus via `HandlerConfig`). Full 3-tier activable via `--lead-agent`.

---

## Layer 2: Orchestration Communication Patterns

StartD8 has four distinct orchestration patterns, each with a different communication topology:

### Pattern 1: Sequential Pipeline

**Implementation**: `Pipeline` in `orchestration.py`
**Topology**: Linear chain — each agent's output becomes the next agent's input

```text
Agent 1 ──[text]──▶ transform() ──[text]──▶ Agent 2 ──[text]──▶ transform() ──▶ Agent 3
```

**Data format**: Plain-text strings. Optional `transform: Callable[[str], str]` between steps.
**State**: `PipelineResult.steps` stores per-step metadata.
**Branching**: `ConditionalStep` uses a predicate function to route.

**Limitations**:
- No structured message format between steps (just strings)
- No bidirectional communication
- No agent-to-agent negotiation or consensus
- Transform functions are the only point of data shaping

### Pattern 2: Parallel Fanout

**Implementation**: `ParallelStep` in `orchestration.py`
**Topology**: Same input to N agents simultaneously; outputs aggregated

```text
              ┌──▶ Agent A ──┐
Input ────────┼──▶ Agent B ──┼──▶ aggregator() ──▶ Output
              └──▶ Agent C ──┘
```

**Aggregation**: Custom `aggregator: Callable[[List[str]], str]` combines outputs.
**Use case**: Multi-model comparison, benchmark runs, CRP review rounds (sequential variant).

### Pattern 3: Phase-Based Context Sharing (Artisan)

**Implementation**: `context_seed_handlers.py`, `artisan_phases/`
**Topology**: 7 sequential phases sharing a mutable context dictionary

```text
PLAN ──[context]──▶ SCAFFOLD ──[context]──▶ DESIGN ──[context]──▶ IMPLEMENT ──[context]──▶ TEST ──[context]──▶ REVIEW ──[context]──▶ FINALIZE
```

**Data format**: `context: dict[str, Any]` — each phase reads keys set by prior phases and writes new keys.

**Per-phase context contract** (from AR-1xx):

| Phase | Reads | Writes |
|-------|-------|--------|
| **PLAN** | `enriched_seed_path` | `tasks`, `task_index`, `plan_title`, `plan_goals`, `domain_summary`, `preflight_summary`, `total_estimated_loc`, `architectural_context`, `design_calibration`, `example_artifacts` |
| **SCAFFOLD** | `tasks`, `task_index` | `scaffold` (directories_needed, directories_exist, directories_created, existing_target_files, skipped_targets, project_root) |
| **DESIGN** | `tasks`, `task_index`, `architectural_context`, `design_calibration` | `design_results` (per-task: design_document, status, agreed, iterations, cost) |
| **IMPLEMENT** | `tasks`, `design_results`, `scaffold` | `implementation`, `generation_results`, `_downstream_map`, `_llm_cost_usd` |
| **TEST** | `tasks`, `implementation` | `test_results` (test_plan, total_passed, total_failed, per_task) |
| **REVIEW** | `tasks`, `generation_results` | `review_results` (review_items, total_cost, total_passed, total_failed, per_task) |
| **FINALIZE** | All prior context | `workflow_summary` |

**Agent calls within phases**: Each phase handler calls `agent.agenerate(prompt)` or `agent.generate(prompt)` internally. The orchestrator does not see individual agent calls — it sees phase-level results.

**Validation (Phase 1)**:
- Context dict is validated at every phase boundary by Pydantic v2 models (`context_schema.py`)
- `validate_phase_entry()` checks required keys before handler runs
- `validate_phase_exit()` checks expected output keys after handler completes
- Remaining gap: no checksums on context state between phases (B-14, Phase 4)

### Pattern 4: Iterative Append-Only Review (CRP)

**Implementation**: `architectural_review_log_workflow.py`
**Topology**: N sequential reviewers, each appending to a shared document

```text
Reviewer 1 ──[append to Appendix C]──▶ Triage ──[A or B]──▶ Reviewer 2 ──[append]──▶ Triage ──▶ ...
```

**Data format**: Structured 7-column markdown table (ID, Area, Severity, Suggestion, Rationale, Proposed Placement, Validation Approach).

**Protocol**: Convergent Review Protocol (CRP) — see [ARCHITECTURAL_REVIEW_REQUIREMENTS.md](../ARCHITECTURAL_REVIEW_REQUIREMENTS.md).

**Key difference from other patterns**: The "message" between reviewers is the document itself. Each reviewer sees the full document plus all prior review rounds (Appendix C), all applied suggestions (Appendix A), and all rejected suggestions with rationale (Appendix B). Domain coverage tracking steers later reviewers toward uncovered areas.

---

## Layer 3: Context Propagation Protocol

This is the highest-value layer for formalization. The artisan issues catalog traces multiple bugs to unvalidated context mutations (A-1 multi-file split, A-4 LOC mismatch, A-5 stale cache, A-12 hollow defense layers, A-13 flat calibration).

### Current State

Context propagation uses a mutable `dict[str, Any]` passed through all phases:

```python
context = {}  # Created by orchestrator
plan_handler.execute(context, agents, ...)    # PLAN writes keys
scaffold_handler.execute(context, agents, ...) # SCAFFOLD reads PLAN keys, writes own
design_handler.execute(context, agents, ...)   # DESIGN reads PLAN+SCAFFOLD keys, writes own
# ... etc
```

**Schema enforcement** is now active at every phase boundary via Pydantic v2 models in `context_schema.py` (Phase 1). `validate_phase_entry()` and `validate_phase_exit()` are called in `_execute_phase()` to catch type errors and missing keys at the point of failure.

### ContextCore Data Flow — Implemented (Phase 2)

The [`ARTISAN_CONTEXTCORE_DATA_FLOW_FIXES.md`](../plans/ARTISAN_CONTEXTCORE_DATA_FLOW_FIXES.md) fixes are now implemented:

| Fix | Priority | What It Does | Status |
|-----|----------|-------------|--------|
| **Fix 1**: Provenance chain | High | PLAN extracts `source_checksum` from seed; FINALIZE records it in manifest for Gate 3 | Implemented |
| **Fix 2**: `parameter_sources` | Medium | Propagated from onboarding → seed → PLAN context → DESIGN/IMPLEMENT prompts | Implemented |
| **Fix 3**: `semantic_conventions` | Medium | Same propagation pattern as Fix 2 for metric names, label conventions | Implemented |
| **Fix 4**: Provenance in manifest | Medium | Merged with Fix 1b — FINALIZE includes provenance block | Implemented |
| **Fix 5**: `output_conventions` | Low | SCAFFOLD validates file extensions against onboarding conventions (warn-only) | Implemented |

### Enrichment Data Flow (Current State)

The context propagation for ContextCore-enriched workflows is:

```text
.contextcore.yaml ──export──▶ onboarding-metadata.json
                                   │
                    ┌───────────────┼───────────────┬──────────────────┐
                    ▼               ▼               ▼                  ▼
              source_checksum  parameter_sources  semantic_conventions  output_conventions
                    │               │               │                  │
              plan-ingestion ──seed.json──▶ PLAN phase context
                    │               │               │                  │
              FINALIZE manifest  DESIGN prompts   DESIGN prompts    SCAFFOLD validation
              (Gate 3 compat)   IMPLEMENT chunks  IMPLEMENT chunks  (extension check)
```

### Context Key Categories

| Category | Keys | Immutability | Source |
|----------|------|-------------|--------|
| **Seed identity** | `enriched_seed_path` | Immutable after PLAN | CLI args |
| **Task graph** | `tasks`, `task_index` | Immutable after PLAN | Seed JSON |
| **Plan metadata** | `plan_title`, `plan_goals`, `domain_summary` | Immutable after PLAN | Seed JSON |
| **Provenance** | `source_checksum` | Immutable (planned) | Seed → onboarding |
| **Enrichment** | `parameter_sources`, `semantic_conventions`, `output_conventions` | Immutable (planned) | Seed → onboarding |
| **Quality calibration** | `architectural_context`, `design_calibration`, `example_artifacts` | Immutable after PLAN | Seed → manifest/onboarding |
| **Phase outputs** | `scaffold`, `design_results`, `implementation`, `generation_results`, `test_results`, `review_results` | Written once per phase | Phase handlers |
| **Accumulator** | `_llm_cost_usd`, `_downstream_map` | Mutable (accumulated) | Phase handlers |
| **Diagnostics** | `preflight_summary`, `total_estimated_loc` | Immutable after PLAN | Preflight + seed |

### Open Issues in Context Propagation

| Issue ID | Description | Impact | Status |
|----------|------------|--------|--------|
| B-12 | Seed schema validation advisory-only | Malformed seeds get warnings but write anyway | Partially addressed (Phase 1) |
| B-14 | No context file checksums in handoff | Context drift between design and implement undetected | Addressed (Phase 4) |
| B-15 | No shared schema version across pipeline artifacts | No compatibility branching | Open (Phase 4) |
| ~~B-16~~ | ~~Incomplete provenance chain~~ | ~~Gate 3 cannot verify pipeline integrity~~ | Addressed (Phases 2+3) |
| A-12 | Seed lacks `_file_scope` and `file_ownership` | Defense-in-depth layers structurally present but functionally inert | In progress |
| A-13 | Flat design calibration | All tasks get same depth tier regardless of artifact type | In progress |
| A-14 | Missing derivation rules, coverage, dependency graph in seed | DESIGN guesses derivation mappings; tasks generated in arbitrary order | In progress |

---

## Layer 4: Handoff Protocol

### Design-to-Implementation Handoff (Implemented)

The artisan workflow supports a two-half split: design half (PLAN → SCAFFOLD → DESIGN) produces a `HandoffData` JSON file consumed by the implementation half (IMPLEMENT → TEST → REVIEW → FINALIZE).

```text
Design Half                              Implementation Half
PLAN → SCAFFOLD → DESIGN ──────────────▶ IMPLEMENT → TEST → REVIEW → FINALIZE
                           │
                    design-handoff.json
                    (HandoffData model)
```

**HandoffData contents**:
- `design_results`: per-task design documents and review verdicts
- `tasks`: task list with metadata
- `plan_metadata`: title, goals, domain summary
- `scaffold`: directory creation results
- `schema_version`: integer (currently 2, via checkpoint schema)

**Gap** (Issue B-13): No formal JSON schema for `design-handoff.json`. The `HandoffData` dataclass provides Python-side structure but no cross-language schema for validation.

**Gap** (Issue B-14): **Addressed (Phase 4).** Context file checksums are now computed at handoff write time and verified on load. The `--strict-handoff` flag converts mismatch warnings into hard errors.

### Pipeline Step Handoff

In `Pipeline` orchestration, handoff is implicit: each step's text output becomes the next step's text input, optionally transformed.

**No structured handoff** — the "contract" between steps is the transform function's expected input/output format, which is not validated.

### Workflow-to-Sub-Workflow Delegation

`WorkflowStep` in `orchestration.py` delegates to a sub-workflow. The sub-workflow receives `config: Dict[str, Any]` and returns `WorkflowResult`.

**No contract inheritance** — the sub-workflow's config schema is independent of the parent's context.

---

## Layer 5: Event-Driven Communication

### Event Bus (Implemented)

`EventBus` provides a publish-subscribe notification system:

```text
Phase Handler ──emit──▶ EventBus ──dispatch──▶ Subscriber handlers
                          │
                   Event(type, source, data, correlation_id)
```

**Event types** (from `EventType` enum):
- `AGENT_CALL_START`, `AGENT_CALL_COMPLETE` — agent lifecycle
- `WORKFLOW_START`, `WORKFLOW_COMPLETE` — workflow lifecycle
- `PHASE_START`, `PHASE_COMPLETE` — artisan phase lifecycle
- `TRUNCATION_DETECTED`, `TRUNCATION_WARNING`, `TRUNCATION_PREFLIGHT_REJECT` — code safety
- `COST_THRESHOLD_WARNING`, `COST_THRESHOLD_EXCEEDED` — budget alerts

**Limitations**:
- Events are **one-way notifications**, not messages — no request-response pattern
- No guaranteed delivery or acknowledgment
- Agents do not subscribe to events — only orchestrators and observers do
- No agent-to-agent events
- Correlation via `correlation_id` strings (manual, not enforced)

### Where Events Bridge to ContextCore

The `ContextCoreWorkflowAdapter` in `integrations/contextcore.py` wraps workflow execution with OTel span tracking, converting internal events into ContextCore-observable telemetry:

- `PHASE_START` / `PHASE_COMPLETE` → OTel spans with `CONTEXTCORE_PROJECT_ID`, `CONTEXTCORE_TASK_ID` attributes
- `COST_THRESHOLD_EXCEEDED` → budget gate signals visible via TraceQL queries
- Event correlation IDs can be matched to ContextCore `trace_id` for end-to-end observability

---

## Layer 6: Cost and Token Flow

### Per-Call Tracking

Every `BaseAgent.agenerate()` call returns `token_usage: dict` containing provider-specific token counts. Utility functions normalize this:

- `token_usage_input(response)` → input token count
- `token_usage_output(response)` → output token count
- `token_usage_cost(response)` → estimated USD cost

### Accumulation in Context

Artisan phases accumulate cost in the shared context:

```python
context["_llm_cost_usd"] = context.get("_llm_cost_usd", 0.0) + round_cost
```

### Budget Enforcement

| Mechanism | Implementation | Behavior |
|-----------|---------------|----------|
| **Artisan cost budget** | `ArtisanContractorWorkflow` (AR-204) | Configurable `--max-cost` per run; checked after each phase |
| **CRP cost guardrails** | `architectural-review-log` (RV-802, RV-803) | `warn_cost_usd` logs warning; `max_cost_usd` triggers fail-fast |
| **Cost projection** | AR-209 (planned) | Pre-phase cost estimation; abort before exceeding budget |

### Cost Reporting

FINALIZE aggregates cost across implementation, test, and review phases into the generation manifest:

```json
{
  "summary": {
    "cost": {
      "implementation_usd": 1.23,
      "test_usd": 0.45,
      "review_usd": 0.67,
      "total_usd": 2.35
    }
  }
}
```

---

## Layer 7: ContextCore Bridge

### Where StartD8 Meets ContextCore Governance

The pipeline boundary between ContextCore governance and StartD8 execution occurs at two points:

**Ingress** (Gate 2 → Step 4/6): ContextCore's `a2a-diagnose` validates plan ingestion output before StartD8's artisan workflow begins. The enriched context seed is the contract artifact.

**Egress** (Step 4/6 → Gate 3): StartD8's FINALIZE phase produces `generation-manifest.json`, which ContextCore's Gate 3 reads to verify provenance, task completion, and artifact checksums.

### Adapter: `integrations/contextcore.py`

| Class | Role |
|-------|------|
| `ContextCoreConfig` | Configuration for project/task/sprint IDs |
| `ContextCoreWorkflowAdapter` | Wraps workflows with OTel span tracking |
| `ContextCoreTaskRunner` | Multi-task runner with dependency resolution |

### Provenance Chain (Implemented — Phases 2 + 3)

```text
.contextcore.yaml ──sha256──▶ onboarding-metadata.json (source_checksum)
                                       │
                              plan-ingestion preflight: verifies checksum against .contextcore.yaml
                                       │
                              plan-ingestion seed.json (source_checksum)
                                       │ PLAN phase extracts + stores in context
                              artisan context["source_checksum"]
                                       │ FINALIZE records in manifest
                              generation-manifest.json (provenance.source_checksum)
                                       │
                              Gate 3: a2a-diagnose reads and verifies
```

### Contract Type Mapping

| ContextCore Contract | StartD8 Equivalent | Gap |
|---------------------|-------------------|-----|
| `TaskSpanContract` | OTel spans from `ContextCoreWorkflowAdapter` | Spans exist; not yet structured as formal contracts |
| `HandoffContract` | `HandoffData` (design → implement split) | **Addressed (Phase 4)**: `wrap_handoff_in_contract()` wraps HandoffData in a ContextCore HandoffContract; `design-handoff-contract.json` written alongside handoff |
| `ArtifactIntent` | `design_results` per-task entries | Design results are rich but not ArtifactIntent-shaped |
| `GateResult` | Snippet validation (CRP), review scores (artisan) | **Addressed (Phase 4)**: `GateEmitter` in `gate_contracts.py` maps review scores, checkpoint results, and preflight reports to typed GateResult contracts emitted via EventBus |

---

## Gap Analysis Summary

### Gaps Closed by Phases 1–3

| Gap | Fix Applied | Phase |
|-----|-----------|-------|
| Broken provenance chain | Fix 1: source_checksum in PLAN + FINALIZE + preflight verification | Phase 2 + 3 |
| LLM prompts lack parameter sources | Fix 2: parameter_sources injected into DESIGN/IMPLEMENT prompts | Phase 2 |
| LLM prompts lack semantic conventions | Fix 3: semantic_conventions injected into DESIGN/IMPLEMENT prompts | Phase 2 |
| No output convention validation | Fix 5: SCAFFOLD extension check (warn-only) | Phase 2 |
| No export preflight at ingestion | `_preflight_export_contract()` with `preflight-report.json` | Phase 3 |
| No traceability artifact | `ingestion-traceability.json` with `refine_impact` | Phase 3 |
| No context schema validation | Pydantic v2 models with `validate_phase_entry()`/`validate_phase_exit()` | Phase 1 |
| No handoff JSON schema | `_validate_handoff()` now always-on; cross-validation function added | Phase 1 |

### Remaining Structural Gaps (Phase 4 Scope)

| Gap | Description | Priority |
|-----|------------|----------|
| **No message protocol between pipeline steps** | Pipeline steps exchange raw strings; no envelope, no metadata | Medium — limits composability |
| **No agent capability declaration** | Agents don't express what they can do; orchestrators must know | Low — current architecture doesn't need it |
| **No request-response events** | EventBus is notification-only; no way to ask an agent a question via events | Low — orchestrator-centric model handles this |
| **Events not emitted as ContextCore GateResults** | Internal quality gates (snippet validation, review scores) produce ad-hoc results, not typed GateResult contracts | Addressed (Phase 4) |
| **No context checksums in handoff** | Design-to-implement handoff doesn't detect context drift (B-14) | Addressed (Phase 4) |
| **No shared schema version** | Seed, handoff, and manifest use independent version schemes (B-15) | Low |

---

## Implementation Priority (Recommended)

Given the deliberate pause to polish requirements, the recommended sequence is:

### Phase 1: Context Contract (High Value, Low Risk) — COMPLETED

1. **Define context key schema** — Pydantic v2 models for per-phase read/write contract (`context_schema.py`)
2. **Add boundary validation** — `validate_phase_entry()` / `validate_phase_exit()` at every phase boundary
3. **Add `design-handoff.json` schema** — close Issue B-13; `_validate_handoff()` now always-on

### Phase 2: Data Flow Fixes (High Value, Scoped) — COMPLETED

4. **Fix 1** — provenance chain (source_checksum in PLAN + FINALIZE manifest) — Gate 3 compatible
5. **Fixes 2+3** — parameter_sources and semantic_conventions propagated from onboarding → seed → PLAN → DESIGN/IMPLEMENT prompts
6. **Fix 5** — output convention validation in SCAFFOLD (warn-only extension check)

### Phase 3: Ingestion Strengthening — COMPLETED

7. **Export preflight hardened** (Recommendation 2) — source_checksum verified against `.contextcore.yaml`; `preflight-report.json` artifact emitted for downstream gating
8. **Traceability artifact hardened** (Recommendation 6) — `ingestion-traceability.json` includes `refine_impact` (before/after metrics from CRP refinement)
9. **Requirements-aware refine** (Recommendation 5) — CRP dual-document mode wired into plan ingestion; Prime YAML output enriched with `requirement_ids`, `acceptance_obligations`, `source_references`

### Phase 4: Cross-System Integration — COMPLETED

10. **Emit GateResult contracts** from internal quality gates — makes StartD8 quality signals visible to ContextCore governance dashboards (Implemented in `gate_contracts.py` + `ReviewPhaseHandler` + `PreflightReport`)
11. **Wrap HandoffData in HandoffContract** — enables ContextCore to validate design→implement handoffs (Implemented in `handoff.py`)
12. **Add context checksums to handoff** — close Issue B-14; detect context drift (Implemented in `handoff.py` + `run_artisan_implement_only.py`)

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix implements the **Convergent Review Protocol (CRP)** — an iterative, domain-aware review process that converges toward full coverage. It is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
