# Plan-to-Design Bridge — Functional Requirements

**Version:** 1.0.0
**Created:** 2026-02-23
**Status:** Planned (0/16 implemented)
**Source:** Mottainai audit (Gaps 4, 6, 8, 22), Artisan Internal Audit (Anti-Pattern 2), Run 1 artisan waste analysis ($2.61 on 17 tasks)
**Prerequisite reading:**
- [Mottainai Design Principle](design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) — Gaps 4, 6, 8, 22 and Anti-Pattern 2 define the problem
- [REFINE Forwarding Requirements](REFINE_FORWARDING_REQUIREMENTS.md) — Pattern template (4-layer structure, REQ-RF-001..012)
- [Artisan Functional Requirements](design/artisan/ARTISAN_REQUIREMENTS.md) — AR-120..128 (DESIGN phase), AR-900..908 (Mottainai compliance)
- [`startd8.artisan.functional-requirements.yaml`](capability-index/startd8.artisan.functional-requirements.yaml) — Canonical YAML format

---

## Overview

### Problem Statement

The Capability Delivery Pipeline runs Plan Ingestion (PARSE → ASSESS → TRANSFORM → REFINE → EMIT) before the Artisan Contractor (PLAN → SCAFFOLD → DESIGN → IMPLEMENT → INTEGRATE → TEST → REVIEW → FINALIZE). Plan Ingestion performs significant design-level work:

- **TRANSFORM** produces architecture, risk register, and verification strategy sections in `PLAN-ingested.md`
- **REFINE** runs an LLM architectural review (~$0.50–$2.00) with structured suggestions (now forwarded via REQ-RF-001..006)
- **ASSESS** scores complexity across 7 dimensions (`feature_count`, `cross_file_deps`, `api_surface`, `test_complexity`, `integration_depth`, `domain_novelty`, `ambiguity`)
- **EMIT** writes tasks with LOC estimates, dependency graphs, `design_doc_sections`, `api_signatures`, and `negative_scope`

The DESIGN phase starts from scratch — it generates designs without awareness of TRANSFORM's architecture, ASSESS's complexity scores, or EMIT's task-level hints beyond `design_doc_sections` and `negative_scope`. This violates the Mottainai principle: **every artifact produced by an earlier stage carries invested computation, context, and deterministic correctness. Discarding it is mottainai.**

### Evidence

Run 1 artisan: the DESIGN phase spent **$2.61** on 17 tasks re-deriving architecture, parameters, and risk analysis that Plan Ingestion had already computed. 11 design documents were generated before the run was manually killed. The DESIGN LLM independently re-derived architectural decisions, risk mitigations, and verification strategies that existed in `PLAN-ingested.md` — a document DESIGN never reads.

### Scope

This document formalizes Plan Ingestion output as the DESIGN phase's foundation. It does NOT cover:
- REFINE suggestion forwarding (already closed by REQ-RF-001..012)
- IMPLEMENT consumption of design results (covered by AR-130..137, AR-1020..1024)
- Prime contractor route (covered by Mottainai Gaps 9–14)

### Status Dashboard

| Layer | ID Range | Total | Implemented | Planned |
|-------|----------|-------|-------------|---------|
| Foundation Injection | REQ-PD-001–004 | 4 | 0 | 4 |
| Elaboration Framing | REQ-PD-005–008 | 4 | 0 | 4 |
| Delta-Awareness | REQ-PD-009–012 | 4 | 0 | 4 |
| Provenance and Observability | REQ-PD-013–016 | 4 | 0 | 4 |
| **Total** | | **16** | **0** | **16** |

---

## Data Flow

### Current State (Pre-Implementation)

```
Plan Ingestion                        Artisan Contractor
─────────────                         ──────────────────
PARSE → ASSESS → TRANSFORM → REFINE → EMIT
   │        │         │          │       │
   │        │         │          │       ├── artisan-context-seed.json
   │        │         │          │       │   ├── tasks[] (with design_doc_sections, api_signatures,
   │        │         │          │       │   │           negative_scope, protocol)
   │        │         │          │       │   ├── complexity (composite + 7 dimensions)
   │        │         │          │       │   ├── wave_metadata
   │        │         │          │       │   └── onboarding.refine_suggestions ✓ (REQ-RF-004)
   │        │         │          │       │
   │        │         │          │       └── PLAN-ingested.md
   │        │         │               ├── Architecture section      ◄── NOT read by DESIGN
   │        │         │               ├── Risk Register section     ◄── NOT read by DESIGN
   │        │         │               └── Verification Strategy     ◄── NOT read by DESIGN
   │        │
   │        └── complexity.dimensions   ◄── NOT forwarded to DESIGN context
   │
   └── tasks[].requirements_text = ""  ◄── EMPTY (not populated by EMIT)

                    PLAN phase ──► SCAFFOLD ──► DESIGN
                      │                           │
                      │                           ├── Has: plan_document_text (raw text)
                      │                           ├── Has: refine_suggestions (REQ-RF)
                      │                           ├── Missing: structured TRANSFORM sections
                      │                           ├── Missing: complexity_dimensions
                      │                           ├── Missing: requirements_text per task
                      │                           ├── Missing: api_signatures injection
                      │                           ├── Missing: protocol injection
                      │                           ├── Missing: foundation-aware prompt mode
                      │                           └── Missing: dependency-ordered cross-task context
```

### Target State (Post-Implementation)

```
Plan Ingestion EMIT ──► artisan-context-seed.json
                           │
                           ├── tasks[].requirements_text  ◄── REQ-PD-003
                           ├── complexity.dimensions       ◄── already in seed
                           └── wave_metadata               ◄── already in seed

                    PLAN phase ──► SCAFFOLD ──► DESIGN
                      │               │           │
                      │               │           ├── Foundation blocks from TRANSFORM doc  (REQ-PD-001)
                      │               │           ├── Complexity-calibrated depth guidance   (REQ-PD-002)
                      │               │           ├── requirements_text per task             (REQ-PD-003)
                      │               │           ├── api_signatures + protocol injection    (REQ-PD-004)
                      │               │           ├── Foundation-aware system prompt          (REQ-PD-005)
                      │               │           ├── Elaboration-aware refine prompt         (REQ-PD-006)
                      │               │           ├── Dependency-ordered cross-task context   (REQ-PD-007)
                      │               │           ├── Wave position context                   (REQ-PD-008)
                      │               │           ├── Staleness-aware design mode             (REQ-PD-009)
                      │               │           ├── Source checksum drift detection         (REQ-PD-010)
                      │               │           ├── Plan-delta indicators                   (REQ-PD-011)
                      │               │           ├── Foundation coverage metric              (REQ-PD-012)
                      │               │           ├── Chain status logging                    (REQ-PD-013)
                      │               │           ├── Foundation provenance in results        (REQ-PD-014)
                      │               │           ├── Artifact inventory extension            (REQ-PD-015)
                      │               │           └── Contract YAML update                    (REQ-PD-016)
```

### ContextCore Propagation Chain Declarations

```yaml
propagation_chains:

  - chain_id: plan_transform_to_design
    description: >
      TRANSFORM-phase plan document sections (Architecture, Risk Register,
      Verification Strategy) flow through the context seed and PLAN phase
      into DESIGN, where they serve as labeled foundation blocks with
      "elaborate, don't regenerate" framing.
    source:
      phase: ingestion.transform
      field: plan_document_text
    waypoints:
      - phase: emit
        field: artifacts.plan_document_path
      - phase: artisan.plan
        field: plan_document_text
    destination:
      phase: artisan.design
      field: additional_context.plan_architecture + additional_context.plan_risks
    severity: warning
    verification: "len(dest.plan_architecture) > 0 or len(dest.plan_risks) > 0"

  - chain_id: complexity_to_design_calibration
    description: >
      ASSESS-phase complexity dimensions flow through the seed into DESIGN,
      where high-scoring dimensions trigger complexity-specific design
      guidance (e.g., "high api_surface: design API contracts in detail").
    source:
      phase: ingestion.assess
      field: complexity.dimensions
    waypoints:
      - phase: emit
        field: seed.complexity.dimensions
    destination:
      phase: artisan.design
      field: additional_context.complexity_guidance
    severity: advisory
    verification: "dest is not None when source.composite > 60"

  - chain_id: dependency_graph_to_design_ordering
    description: >
      Task dependency graph from EMIT determines DESIGN task ordering,
      ensuring dependent tasks receive designs of their declared
      dependencies rather than chronologically-prior designs.
    source:
      phase: ingestion.emit
      field: tasks[].depends_on
    waypoints:
      - phase: artisan.plan
        field: task_index + wave_assignments
    destination:
      phase: artisan.design
      field: dependency_designs (in additional_context)
    severity: advisory
    verification: "for each dep in task.depends_on: dep in design_results"
```

---

## Layer 1: Foundation Injection (REQ-PD-001–004)

Injects Plan Ingestion's structured output into the DESIGN phase's `FeatureContext` and `additional_context`, providing a foundation that DESIGN elaborates rather than regenerates.

### REQ-PD-001: TRANSFORM Document Structured Injection

**Status:** planned
**Closes:** Mottainai Gap 8 (plan document sections not read by DESIGN)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler._task_to_feature_context`, ~line 1816)
**Depends on:** AR-1002 (plan_document_text forwarded to context)

DESIGN MUST inject the plan document's Architecture, Risk Register, and Verification Strategy sections as labeled foundation blocks in `additional_context`, with "elaborate, don't regenerate" framing.

**Acceptance criteria:**

1. `_task_to_feature_context()` extracts "Architecture", "Risk Register" (or "Risk"), and "Verification Strategy" (or "Verification") sections from `inv_plan_document` using `_extract_plan_section()`.
2. Each extracted section is injected into `additional_context` under keys `plan_architecture`, `plan_risks`, and `plan_verification_strategy` respectively.
3. Each injected block is prefixed with: `"FOUNDATION (from Plan Ingestion TRANSFORM — elaborate and add implementation detail, do NOT regenerate from scratch):\n"`.
4. The combined character count of all three foundation blocks MUST NOT exceed 6000 characters. When exceeded, sections are truncated in priority order: verification strategy first, then risk register, then architecture (architecture is highest priority).
5. When a section is absent from the plan document, the corresponding `additional_context` key is omitted (graceful degradation per Mottainai Rule 3). No error or warning is logged for absent sections — this is the expected case when Plan Ingestion did not run TRANSFORM.
6. The existing `plan_architecture` and `plan_risks` injection logic (~line 1816–1826) is preserved and extended — this requirement adds the "FOUNDATION" prefix and verification strategy, not a rewrite.

**Rationale:** Run 1 artisan spent $2.61 re-deriving architecture and risk analysis that TRANSFORM had already computed. The "elaborate, don't regenerate" framing prevents the DESIGN LLM from discarding the foundation and starting fresh.

---

### REQ-PD-002: Complexity-Aware Design Depth Calibration

**Status:** planned
**Closes:** Mottainai Gap 6 (complexity scoring not forwarded to DESIGN)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler._task_to_feature_context`), `src/startd8/workflows/builtin/plan_ingestion_models.py` (`ComplexityScore`)

When complexity dimensions are available in the seed, DESIGN MUST use them to calibrate design depth guidance per dimension.

**Acceptance criteria:**

1. `PlanPhaseHandler.execute()` extracts `seed_data.get("complexity", {}).get("dimensions", {})` from the seed and stores it in `context["complexity_dimensions"]` as a `Dict[str, int]` (7 keys: `feature_count`, `cross_file_deps`, `api_surface`, `test_complexity`, `integration_depth`, `domain_novelty`, `ambiguity`).
2. `DesignPhaseHandler._task_to_feature_context()` accepts a new `complexity_dimensions: Dict[str, int] | None` parameter. When any individual dimension scores >70, `additional_context["complexity_guidance"]` includes dimension-specific instructions:
   - `api_surface > 70`: "High API surface complexity: design API contracts, endpoint signatures, and request/response schemas in full detail."
   - `cross_file_deps > 70`: "High cross-file dependency complexity: explicitly map import chains and shared module interfaces."
   - `integration_depth > 70`: "High integration depth: document integration points, protocol boundaries, and error propagation paths."
   - `test_complexity > 70`: "High test complexity: include test strategy with edge cases and integration test scenarios."
   - `domain_novelty > 70`: "High domain novelty: include domain concept glossary and reference materials."
   - `ambiguity > 70`: "High ambiguity: flag assumptions explicitly and propose alternatives for ambiguous requirements."
   - `feature_count > 70`: "High feature density: design for modularity and clear interface boundaries between features."
3. When the composite score exceeds 60, `depth_guidance` is upgraded to `"comprehensive"` (unless already set by calibration).
4. When `complexity_dimensions` is `None` or absent, no complexity guidance is injected (graceful degradation). No warning — this is the expected case for seeds without ASSESS data.

---

### REQ-PD-003: `requirements_text` Population from Plan

**Status:** planned
**Closes:** New gap (requirements_text is always empty)
**Source files:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py` (`_phase_emit` — primary modification target)
**Verification target:** `src/startd8/contractors/context_seed_handlers.py` (`SeedTask.from_seed_entry` — already reads the field, no modification needed)

Plan Ingestion's EMIT phase MUST populate `config.requirements_text` for each task from the parsed feature's description, acceptance obligations, and source references.

**Acceptance criteria:**

1. During artisan seed construction in `_phase_emit()`, each task entry's `config.requirements_text` is populated by concatenating:
   - Feature description (from `ParsedFeature.description`)
   - Acceptance obligations (from `ParsedFeature.acceptance_obligations`, if present), formatted as a bulleted list prefixed with "Acceptance criteria:\n"
   - Source references (from `ParsedFeature.source_references`, if present), formatted as "References: {refs}"
2. The concatenated text is capped at 2000 characters. When truncated, the text ends with `" [truncated]"`.
3. When a feature has no description (empty string), `requirements_text` remains `""` (not `None`).
4. `SeedTask.from_seed_entry()` already reads `config.requirements_text` (~line 642) — no change needed on the consumer side.
5. `FeatureContext.requirements_text` (~line 179 in `design_documentation.py`) already receives this field via `_task_to_feature_context()` (~line 1934) — no change needed on the DESIGN consumer side.

**Rationale:** `requirements_text` flows from seed through `SeedTask` through `FeatureContext` to the DESIGN prompt, but is always empty because EMIT never populates it. The wiring exists — only the source is missing.

---

### REQ-PD-004: Task-Level Design Hints Full Consumption

**Status:** planned
**Closes:** Mottainai Gap 8 (task-level — `api_signatures` and `protocol` not consumed by DESIGN)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler._task_to_feature_context`, ~line 1740)

DESIGN MUST consume ALL task-level hints from the seed: `api_signatures` and `protocol`. (`design_doc_sections` and `negative_scope` are already consumed.)

**Acceptance criteria:**

1. When `task.api_signatures` is non-empty, `_task_to_feature_context()` injects them into `additional_context["api_signatures"]` with the prefix: `"PLAN-SPECIFIED API SIGNATURES (preserve exactly — these are the contract from plan ingestion):\n"` followed by each signature on its own line.
2. When `task.protocol` is non-empty, `_task_to_feature_context()` injects it into `additional_context["transport_protocol"]` with the text: `"Transport protocol constraint: {protocol}. Design MUST use this protocol for all network interfaces in this feature."`.
3. Both fields degrade gracefully: when empty or absent, the corresponding `additional_context` key is omitted.
4. `api_signatures` are injected as a "preserve exactly" block because they represent a contract from plan ingestion that DESIGN should honor, not re-derive. `protocol` is injected as a hard constraint because transport protocol mismatches (e.g., gRPC-vs-Flask) cause integration failures (see Gap 16, DEV-R2-001).

---

## Layer 2: Elaboration Framing (REQ-PD-005–008)

Adjusts DESIGN prompts to operate in "elaboration mode" when plan foundation data is available — adding implementation detail rather than regenerating from scratch.

### REQ-PD-005: Foundation-Aware System Prompt

**Status:** planned
**Closes:** Mottainai Anti-Pattern 2 (Compute-But-Don't-Forward — DESIGN ignores available foundation)
**Source files:** `src/startd8/contractors/artisan_phases/design_documentation.py` (system prompt construction), `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler._task_to_feature_context`)

When plan foundation data is available, the DESIGN system prompt MUST switch to "Foundation Mode" that instructs the LLM to elaborate on existing analysis rather than generate from scratch.

**Acceptance criteria:**

1. `FeatureContext` gains a `has_plan_foundation: bool` field (default `False`).
2. `_task_to_feature_context()` sets `has_plan_foundation=True` when ANY of the following are present in `additional_context`: `plan_architecture`, `plan_risks`, `plan_verification_strategy`, `refine_suggestions`, `complexity_guidance`.
3. When `has_plan_foundation is True`, the DESIGN system prompt includes: `"Plan Ingestion has already produced architectural analysis, risk assessment, and/or complexity scoring for this project. Your task is to ELABORATE on this foundation — add implementation-level detail, resolve ambiguities, and fill gaps. Do NOT discard or regenerate the foundation analysis."`.
4. When `has_plan_foundation is False`, the system prompt is unchanged from current behavior (zero regression for seeds without plan ingestion data).
5. The foundation mode text is appended to the existing system prompt, not a replacement.

---

### REQ-PD-006: Elaboration-Aware Refine Prompt

**Status:** planned
**Closes:** Mottainai Rule 2 (Forward, don't regenerate — refine prompt must acknowledge both sources)
**Source files:** `src/startd8/contractors/artisan_phases/design_documentation.py` (refine prompt construction)

When a prior design AND plan foundation are both available (the refine path), the refine prompt MUST instruct the LLM to synthesize both inputs rather than favoring one.

**Acceptance criteria:**

1. The refine prompt template gains a `{foundation_block}` placeholder.
2. When `FeatureContext.has_plan_foundation is True` AND `FeatureContext.prior_design is not None`, the refine prompt includes: `"You have two inputs: (1) a prior design document from an earlier run, and (2) plan foundation data from Plan Ingestion. Synthesize both: preserve correct analysis from either source, resolve conflicts in favor of the plan foundation (it was produced from full-project analysis), and add new implementation detail."`.
3. When `has_plan_foundation is False`, the `{foundation_block}` placeholder renders as empty string (zero regression).
4. The foundation block is positioned after the prior design injection and before the "improve and refine" instruction.

---

### REQ-PD-007: Dependency-Ordered Cross-Task Context

**Status:** planned
**Closes:** Mottainai Gap 4 (dependency graph not used for design ordering)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler.execute`, ~line 2335)

Dependent tasks MUST receive the design documents of their declared dependencies (via `depends_on`), not just chronologically-prior designs.

**Acceptance criteria:**

1. After each task's design completes, its design document summary is stored in a `completed_designs: Dict[str, str]` keyed by `task_id`.
2. For each task, `_task_to_feature_context()` receives a new parameter `dependency_designs: Dict[str, str] | None` containing the design document summaries of tasks listed in `task.depends_on` that have already been designed.
3. When `dependency_designs` is non-empty, it is injected into `additional_context["dependency_designs"]` formatted as: `"Designs of tasks this feature depends on:\n"` followed by each dependency's summary (truncated to 500 chars each, max 3 dependencies shown).
4. The existing `prior_design_summaries` parameter (chronological context) is preserved. `dependency_designs` supplements it — both may be present.
5. When a dependency has not yet been designed (e.g., cycle in `depends_on`), it is omitted from `dependency_designs` with a DEBUG log: `"DESIGN: dependency %s for task %s not yet designed — omitting from context"`.

---

### REQ-PD-008: Wave-Aware Context Accumulation

**Status:** planned
**Closes:** Mottainai Gap 4 (dependency ordering — wave boundary awareness)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler.execute`)

DESIGN MUST inject wave position context for tasks with wave assignments, informing the LLM about parallel execution constraints.

**Acceptance criteria:**

1. When `task.wave_index is not None` and `wave_metadata` is available in context, `_task_to_feature_context()` injects `additional_context["wave_context"]` with: `"This task is in wave {wave_index+1} of {wave_count}. Tasks in the same wave execute in parallel — avoid shared mutable state with parallel tasks. Tasks in earlier waves are guaranteed complete."`.
2. At wave boundaries (when `task.wave_index` changes from the previous task), the handler logs INFO: `"DESIGN: entering wave %d of %d (%d tasks in this wave)"`.
3. When `wave_index` is `None` or `wave_metadata` is absent, no wave context is injected (graceful degradation).
4. Wave metadata is read from `context.get("wave_metadata")` which is already populated by `PlanPhaseHandler` (from `compute_wave_metadata(waves)`, ~line 1208).

---

## Layer 3: Delta-Awareness (REQ-PD-009–012)

Enables DESIGN to operate differentially when existing state is available — designing incremental changes rather than full rewrites.

### REQ-PD-009: Staleness-Aware Design Mode

**Status:** planned
**Closes:** Mottainai Gap 22 (SCAFFOLD staleness not forwarded to DESIGN)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler._task_to_feature_context`)

DESIGN MUST consume SCAFFOLD's `staleness_classification` to adjust design guidance per file.

**Acceptance criteria:**

1. `_task_to_feature_context()` accepts a new parameter `staleness_classification: Dict[str, str] | None` (maps file path to `"current"` / `"stale"` / `"unknown"`).
2. For tasks with existing target files classified as `"stale"`, `additional_context["staleness_guidance"]` is set to: `"Target file(s) are classified as STALE (modified since last generation). Focus your design on what needs to change — describe the delta, not a full rewrite."`.
3. For tasks with existing target files classified as `"current"`, `additional_context["staleness_guidance"]` is set to: `"Target file(s) are classified as CURRENT (unchanged since last generation). Minimal changes expected — design should explain why changes are needed despite the file being current."`.
4. For `"unknown"` classification or absent staleness data, no guidance is injected.
5. Staleness data is read from `context.get("scaffold", {}).get("staleness_classification", {})`, which is already populated by `ScaffoldPhaseHandler` (~line 893–927 of `context_seed_handlers.py`) and declared in `artisan-pipeline.contract.yaml` as a DESIGN enrichment input.

---

### REQ-PD-010: Source Checksum Drift Detection

**Status:** planned
**Closes:** New gap (no checksum verification at DESIGN entry)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler.execute`)

DESIGN MUST compare the seed's `source_checksum` against current export state and log the result. Advisory only — does not block.

**Acceptance criteria:**

1. At DESIGN entry, read `context.get("source_checksum")`.
2. If a `source_checksum` is present and the export's `.contextcore.yaml` (or `onboarding-metadata.json`) is accessible, compute the current checksum and compare.
3. Log one of three outcomes:
   - `INFO`: `"DESIGN: source_checksum MATCH — foundation data is current"` (checksums equal)
   - `WARNING`: `"DESIGN: source_checksum MISMATCH — foundation data may be stale (seed: %s, current: %s)"` (checksums differ)
   - `DEBUG`: `"DESIGN: source_checksum UNAVAILABLE — cannot verify foundation freshness"` (no checksum or no export file)
4. This check is advisory only — it MUST NOT block DESIGN execution regardless of outcome.
5. The result is stored in `context["_source_checksum_status"]` as one of `"MATCH"`, `"MISMATCH"`, `"UNAVAILABLE"` for downstream consumption by REQ-PD-014.

---

### REQ-PD-011: Plan-Delta Indicator for Changed Tasks

**Status:** planned
**Closes:** Mottainai Gap 8 (task-level — no detection of plan-vs-calibration drift)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler._task_to_feature_context`)

DESIGN MUST detect when a task's plan-specified hints differ from calibration-derived sections and flag the divergence.

**Acceptance criteria:**

1. When both `task.design_doc_sections` (from plan) AND `calibration.sections` (from size estimator) are non-empty, compare them. If they differ, inject `additional_context["plan_delta"]` with: `"NOTE: Plan-specified design sections differ from calibration. Plan sections: {plan_sections}. Calibration sections: {cal_sections}. Follow plan sections as primary — they reflect project-specific requirements."`.
2. When `task.api_signatures` is non-empty, inject a verification note in `additional_context["api_signature_verification"]`: `"The following API signatures were specified by plan ingestion. Verify their correctness against the architectural context and flag any inconsistencies: {signatures}"`.
3. Both indicators are advisory — they guide the LLM but do not override the primary input.

---

### REQ-PD-012: Foundation Coverage Metric

**Status:** planned
**Closes:** Mottainai Rule 6 (Measure the gap)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler.execute`)

DESIGN MUST compute a foundation coverage metric per task and warn when coverage is low.

**Acceptance criteria:**

1. Foundation coverage is computed as: `foundation_keys / 11` where `foundation_keys` is the count of the following 11 fields that are present (non-None, non-empty). Ten are checked in `additional_context`: `plan_architecture`, `plan_risks`, `plan_verification_strategy`, `refine_suggestions`, `complexity_guidance`, `dependency_designs`, `wave_context`, `api_signatures`, `transport_protocol`, `staleness_guidance`. The eleventh, `requirements_text`, is checked on `FeatureContext.requirements_text` (it is set directly on the dataclass, not in `additional_context`).
2. When foundation coverage < 0.30 (fewer than 4 of 11 keys), log WARNING: `"DESIGN task %s: low foundation coverage %.0f%% (%d/11 fields) — design will rely heavily on LLM inference"`.
3. When foundation coverage >= 0.30, log INFO: `"DESIGN task %s: foundation coverage %.0f%% (%d/11 fields)"`.
4. The coverage value is stored in `design_results[task_id]["foundation_coverage"]` as a float in [0.0, 1.0] for downstream observability.

---

## Layer 4: Provenance and Observability (REQ-PD-013–016)

Provides measurement, audit trail, and contract declarations for the plan-to-design bridge.

### REQ-PD-013: Chain Status Logging at DESIGN Entry

**Status:** planned
**Closes:** Mottainai Rule 6 (Measure the gap)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler.execute`)

DESIGN MUST log the propagation chain status at entry, assessing whether Plan Ingestion data survived the PI → PLAN → DESIGN boundary.

**Acceptance criteria:**

1. At DESIGN entry (before the task loop), compute chain status from context:
   - **INTACT**: `plan_document_text` is present AND at least 3 of the following 7 onboarding fields are present in context (these match the fields forwarded by `PlanPhaseHandler.execute()` at ~lines 1311–1332 and declared in `_PCA_CONTEXT_FIELDS`): `onboarding_derivation_rules`, `onboarding_resolved_parameters`, `onboarding_output_contracts`, `onboarding_calibration_hints`, `onboarding_open_questions`, `onboarding_dependency_graph`, `onboarding_refine_suggestions`. Additionally, REFINE suggestions MUST be available via either `context.get("onboarding_refine_suggestions")` or `inv_refine_suggestions`.
   - **DEGRADED**: `plan_document_text` is present but fewer than 3 onboarding fields are available, OR `plan_document_text` is absent but some onboarding fields are present.
   - **BROKEN**: Neither `plan_document_text` nor any onboarding field is present.
2. Log the chain status:
   - INTACT: `INFO` — `"DESIGN: PI→DESIGN chain INTACT: plan_document + %d/7 onboarding fields + refine_suggestions"`
   - DEGRADED: `WARNING` — `"DESIGN: PI→DESIGN chain DEGRADED: %s available, %s missing"`
   - BROKEN: `WARNING` — `"DESIGN: PI→DESIGN chain BROKEN: no plan ingestion data available — DESIGN will generate from scratch"`
3. Chain status terminology (INTACT/DEGRADED/BROKEN) MUST align with ContextCore's `ChainStatus` vocabulary (per REQ-RF-011 precedent).
4. Store the status string in `context["_pi_design_chain_status"]` for REQ-PD-014.

---

### REQ-PD-014: Foundation Provenance in Design Results

**Status:** planned
**Closes:** Mottainai Rule 4 (Register what you produce)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler.execute`, result serialization)

Each `design_results` entry MUST include a `foundation_provenance` dict recording which plan fields were consumed, enabling downstream phases (IMPLEMENT, REVIEW) to understand what foundation the design was built on.

**Acceptance criteria:**

1. Each `design_results[task_id]` entry includes a `foundation_provenance` dict with:
   - `chain_status`: `"INTACT"` / `"DEGRADED"` / `"BROKEN"` (from REQ-PD-013)
   - `fields_consumed`: list of `additional_context` keys that were populated from plan data (e.g., `["plan_architecture", "refine_suggestions", "complexity_guidance"]`)
   - `foundation_coverage`: float from REQ-PD-012
   - `source_checksum_status`: `"MATCH"` / `"MISMATCH"` / `"UNAVAILABLE"` (from REQ-PD-010)
   - `complexity_composite`: int or None (the composite score from the seed)
2. IMPLEMENT and REVIEW phases can read `design_results[task_id]["foundation_provenance"]` to understand the design's foundation quality without re-computing.
3. The `foundation_provenance` dict is serialized in design result files and survives checkpoint resume.

---

### REQ-PD-015: Artifact Inventory Extension

**Status:** planned
**Closes:** Mottainai Rule 4 (Register what you produce)
**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`DesignPhaseHandler.execute`)

DESIGN MUST register a `plan_to_design_bridge` artifact inventory entry recording the bridge status and coverage metrics.

**Acceptance criteria:**

1. After all tasks complete, DESIGN registers an inventory entry (in the pattern established by `_extend_inventory_with_ingestion`):
   ```json
   {
     "artifact_id": "artisan.plan_to_design_bridge",
     "role": "plan_to_design_bridge",
     "description": "Plan Ingestion → DESIGN bridge status and coverage metrics",
     "produced_by": "startd8.contractors.context_seed_handlers.DesignPhaseHandler",
     "stage": "artisan.design",
     "chain_status": "INTACT",
     "tasks_with_foundation": 14,
     "tasks_without_foundation": 3,
     "mean_foundation_coverage": 0.64,
     "fields_consumed_summary": {
       "plan_architecture": 17,
       "refine_suggestions": 15,
       "complexity_guidance": 12
     },
     "consumers": ["artisan.implement", "artisan.review", "artisan.finalize"]
   }
   ```
2. The inventory entry is appended to `context.setdefault("_artifact_inventory", [])`.
3. When DESIGN runs with zero plan foundation data (chain BROKEN), the entry is still registered with `tasks_with_foundation: 0`.

---

### REQ-PD-016: Contract YAML Update

**Status:** planned
**Closes:** Mottainai Rule 4 (Register what you produce — contract declarations)
**Source files:** `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml`

The artisan pipeline contract YAML MUST declare plan foundation fields as DESIGN enrichment inputs.

**Acceptance criteria:**

1. The `design.entry.enrichment` section gains four new entries:
   ```yaml
   - name: plan_document_text
     type: string
     severity: advisory
     source_phase: plan
     description: "Full plan document text from TRANSFORM phase for foundation injection"
   - name: complexity_dimensions
     type: dict
     severity: advisory
     source_phase: plan
     description: "7-dimension complexity scores from ASSESS phase for design depth calibration"
   - name: onboarding_refine_suggestions
     type: list
     severity: advisory
     source_phase: plan
     description: "Structured REFINE triage suggestions for design foundation"
   - name: wave_metadata
     type: dict
     severity: advisory
     source_phase: plan
     description: "Wave count, summary, and critical path length for wave-aware design context"
   ```
2. All four entries have `severity: advisory` — their absence does not block DESIGN execution.
3. Existing enrichment entries (`scaffold.existing_target_files`, `scaffold.staleness_classification`) are preserved.
4. Schema version remains `0.3.0` (advisory enrichment additions are backward-compatible).

---

## Traceability Matrices

### Requirement → Mottainai Gap

| Requirement | Mottainai Gap/Rule | Description |
|-------------|-------------------|-------------|
| REQ-PD-001 | Gap 8 | TRANSFORM plan document sections not read by DESIGN |
| REQ-PD-002 | Gap 6 | Complexity scoring not forwarded to DESIGN |
| REQ-PD-003 | New gap | `requirements_text` always empty in seed |
| REQ-PD-004 | Gap 8 (task-level) | `api_signatures` and `protocol` not consumed by DESIGN |
| REQ-PD-005 | Anti-Pattern 2 | DESIGN ignores available foundation — compute-but-don't-forward |
| REQ-PD-006 | Rule 2 | Refine prompt must acknowledge both prior design and plan foundation |
| REQ-PD-007 | Gap 4 | Dependency graph not used for design ordering |
| REQ-PD-008 | Gap 4 | Wave boundary awareness for parallel execution |
| REQ-PD-009 | Gap 22 | SCAFFOLD staleness not forwarded to DESIGN |
| REQ-PD-010 | New | Source checksum drift not detected at DESIGN entry |
| REQ-PD-011 | Gap 8 (task-level) | Plan hints vs. calibration divergence undetected |
| REQ-PD-012 | Rule 6 | Foundation coverage not measured |
| REQ-PD-013 | Rule 6 | Chain status not logged at PI → DESIGN boundary |
| REQ-PD-014 | Rule 4 | Foundation provenance not recorded in design results |
| REQ-PD-015 | Rule 4 | Bridge status not registered in artifact inventory |
| REQ-PD-016 | Rule 4 | Plan foundation fields not declared in contract YAML |

### Requirement → Mottainai Rule

| Requirement | Rule Violated | How Requirement Closes It |
|-------------|---------------|---------------------------|
| REQ-PD-001, 003, 004 | Rule 2 (Forward, don't regenerate) | Forwards plan analysis and task hints to DESIGN instead of discarding |
| REQ-PD-005, 006 | Rule 2 | Prompt framing prevents LLM from regenerating existing analysis |
| REQ-PD-002 | Rule 5 (Prefer deterministic over stochastic) | Complexity scores (deterministic) replace LLM depth guessing |
| REQ-PD-007, 008 | Rule 5 | Dependency graph (deterministic) replaces LLM inference of task ordering |
| REQ-PD-009 | Rule 3 (Degrade gracefully) | Staleness data informs design mode with graceful degradation |
| REQ-PD-010, 011 | Rule 3 | Advisory drift detection with graceful degradation |
| REQ-PD-012, 013 | Rule 6 (Measure the gap) | Coverage metrics and chain status quantify foundation utilization |
| REQ-PD-014, 015, 016 | Rule 4 (Register what you produce) | Provenance, inventory, and contracts make the bridge observable |

### Requirement → Source File

| Requirement | Primary Source File | Modification Target |
|-------------|-------------------|-------------------|
| REQ-PD-001 | `context_seed_handlers.py` (~line 1816) | `_task_to_feature_context()` — extend foundation block injection |
| REQ-PD-002 | `context_seed_handlers.py` | `PlanPhaseHandler.execute()` + `_task_to_feature_context()` |
| REQ-PD-003 | `plan_ingestion_workflow.py` (`_phase_emit`) | Artisan seed task construction |
| REQ-PD-004 | `context_seed_handlers.py` (~line 1740) | `_task_to_feature_context()` — add api_signatures + protocol |
| REQ-PD-005 | `design_documentation.py` | System prompt construction |
| REQ-PD-006 | `design_documentation.py` | Refine prompt template |
| REQ-PD-007 | `context_seed_handlers.py` (~line 2335) | `DesignPhaseHandler.execute()` task loop |
| REQ-PD-008 | `context_seed_handlers.py` | `DesignPhaseHandler.execute()` + `_task_to_feature_context()` |
| REQ-PD-009 | `context_seed_handlers.py` | `_task_to_feature_context()` — staleness parameter |
| REQ-PD-010 | `context_seed_handlers.py` | `DesignPhaseHandler.execute()` entry |
| REQ-PD-011 | `context_seed_handlers.py` | `_task_to_feature_context()` — delta detection |
| REQ-PD-012 | `context_seed_handlers.py` | `DesignPhaseHandler.execute()` — per-task metric |
| REQ-PD-013 | `context_seed_handlers.py` | `DesignPhaseHandler.execute()` entry |
| REQ-PD-014 | `context_seed_handlers.py` | `DesignPhaseHandler.execute()` — result serialization |
| REQ-PD-015 | `context_seed_handlers.py` | `DesignPhaseHandler.execute()` — inventory registration |
| REQ-PD-016 | `artisan-pipeline.contract.yaml` | DESIGN enrichment section |

### Requirement → Downstream Consumer

| Requirement | Downstream Consumer | Impact if Missing |
|-------------|-------------------|-------------------|
| REQ-PD-001 | `DesignDocumentationPhase` (LLM prompt) | DESIGN regenerates architecture and risk analysis from scratch ($2.61 wasted on 17 tasks) |
| REQ-PD-002 | `DesignDocumentationPhase` (depth calibration) | Uniform depth for all tasks regardless of complexity — under-designs complex tasks, over-designs simple ones |
| REQ-PD-003 | `FeatureContext.requirements_text` → DESIGN prompt | LLM receives no requirements context per task — designs are structurally correct but may miss acceptance criteria |
| REQ-PD-004 | `DesignDocumentationPhase` (LLM prompt) | API signatures re-derived by LLM — may differ from plan, causing IMPLEMENT/TEST failures |
| REQ-PD-005 | DESIGN system prompt | LLM discards injected foundation blocks and regenerates from scratch |
| REQ-PD-006 | DESIGN refine prompt | Prior design and plan foundation compete rather than synthesize |
| REQ-PD-007 | `DesignDocumentationPhase` (cross-task context) | Dependent tasks designed without awareness of their dependencies' API contracts |
| REQ-PD-008 | `DesignDocumentationPhase` (wave context) | Parallel tasks may design shared mutable state, causing integration failures |
| REQ-PD-009 | `DesignDocumentationPhase` (staleness guidance) | Current files get full-rewrite designs, stale files get fresh-creation designs |
| REQ-PD-010 | Operators / debugging | Stale foundation data produces designs based on outdated context with no warning |
| REQ-PD-011 | `DesignDocumentationPhase` | Divergent plan vs. calibration sections go unnoticed |
| REQ-PD-012 | `design_results`, downstream observability | No measurement of how much plan data reaches DESIGN — cannot quantify bridge effectiveness |
| REQ-PD-013 | Operators / Loki dashboards | No visibility into PI → DESIGN chain health |
| REQ-PD-014 | IMPLEMENT, REVIEW phases | Cannot determine whether design was built on foundation or generated from scratch |
| REQ-PD-015 | Pipeline observability tooling | Bridge status invisible in artifact inventory |
| REQ-PD-016 | Contract validation, `gate_contracts.py` | Plan foundation fields not formally declared — no validation that they propagate |

### Requirement → Existing Requirements

| This Requirement | Existing Requirement | Relationship |
|-----------------|---------------------|-------------|
| REQ-PD-001 | AR-1002 (Forward plan_document_text) | AR-1002 provides the data; REQ-PD-001 structures it for DESIGN consumption |
| REQ-PD-001 | AR-903 (Metadata forwarding) | REQ-PD-001 is a specific instance of AR-903 for plan document sections |
| REQ-PD-002 | AR-121 (Depth calibration) | REQ-PD-002 extends AR-121 with complexity-dimension-specific guidance |
| REQ-PD-003 | REQ-PI-001 (Seed completeness) | REQ-PI-001 lists required seed fields; REQ-PD-003 populates `requirements_text` |
| REQ-PD-004 | AR-125 (Parameter sources) | REQ-PD-004 extends parameter injection to include plan-specified API signatures |
| REQ-PD-005 | AR-120 (Dual-review) | REQ-PD-005 adds a foundation-mode wrapper around the existing dual-review system prompt |
| REQ-PD-007 | AR-124 (Cross-task context) | REQ-PD-007 extends AR-124 from chronological to dependency-ordered context |
| REQ-PD-008 | AR-212 (Wave-parallel) | REQ-PD-008 provides wave awareness to DESIGN; AR-212 uses it for execution |
| REQ-PD-009 | AR-127, AR-128 (Existing file detection, design_mode) | REQ-PD-009 extends existing file awareness with staleness classification |
| REQ-PD-013 | REQ-RF-011 (Chain status logging at EMIT) | REQ-PD-013 mirrors REQ-RF-011's pattern at the DESIGN boundary |
| REQ-PD-016 | AR-308 (Calibration hints in contract) | REQ-PD-016 extends the contract with additional plan foundation fields |

---

## Implementation Priority

| Phase | Requirements | Priority | Rationale |
|-------|-------------|----------|-----------|
| 1 | REQ-PD-001, 003, 004, 005 | **P0** | Foundation injection + prompt framing. Immediate cost savings — closes the $2.61/run waste. Low risk (additive changes to `additional_context` and system prompt). |
| 2 | REQ-PD-002, 006, 007, 008 | **P1** | Calibration + cross-task ordering. Improves design quality through complexity awareness and dependency ordering. Medium complexity (new parameters, prompt template changes). |
| 3 | REQ-PD-009, 010, 011 | **P2** | Delta awareness. Medium complexity — requires staleness data propagation and checksum comparison. Can be implemented in parallel with Phase 2. |
| 4 | REQ-PD-012, 013, 014, 015, 016 | **P3** | Observability layer. Depends on Layers 1–3 to have data to measure. Low implementation risk. |

### Dependency Chain

```
REQ-PD-001 ──┐
REQ-PD-003 ──┤
REQ-PD-004 ──┼──► REQ-PD-005 (needs foundation data to compute has_plan_foundation)
             │         │
             │         └──► REQ-PD-006 (extends refine prompt with foundation awareness)
             │
REQ-PD-002 ──┼──► REQ-PD-012 (needs all fields to compute coverage)
REQ-PD-007 ──┤         │
REQ-PD-008 ──┤         └──► REQ-PD-013, REQ-PD-014 (depends on coverage metric)
REQ-PD-009 ──┤
REQ-PD-010 ──┘
                    REQ-PD-014 ──► REQ-PD-015 (inventory uses provenance data)
                    REQ-PD-016 (independent — contract YAML update)
```

---

## Non-Requirements (Explicitly Out of Scope)

| Topic | Why Out of Scope |
|-------|------------------|
| REFINE suggestion injection into DESIGN | Already closed by REQ-RF-001..006 and implemented as of 2026-02-21. This doc builds on that foundation. |
| Prime contractor route | Covered by Mottainai Gaps 9–14. Plan-to-design bridge is artisan-specific. |
| IMPLEMENT consumption of design results | Covered by AR-130..137 and AR-1020..1024. This doc produces the DESIGN output that IMPLEMENT consumes. |
| Full ContextCore contract YAML for the artisan pipeline | Requires [Pipeline Artifact Inventory Requirements](design-princples/PIPELINE_ARTIFACT_INVENTORY_REQUIREMENTS.md) to land first. REQ-PD-016 adds enrichment entries only. |
| Re-parsing PLAN-ingested.md from disk in DESIGN | Plan text is already loaded by `PlanPhaseHandler` via `plan_document_text`. DESIGN reads it from context, not disk. |
| Modifying `DesignDocumentationPhase.run()` return type | Not needed — all injection goes through `FeatureContext.additional_context` and `FeatureContext` fields. |
| ASSESS phase changes | ASSESS already writes `complexity.dimensions` to the seed. Only PLAN and DESIGN consumption is in scope. |

---

## Related Documents

| Document | Relationship |
|----------|-------------|
| [Mottainai Design Principle](design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Gaps 4, 6, 8, 22 define the violations; Rules 2–6 guide the solution; Anti-Pattern 2 motivates the prompt framing layer |
| [REFINE Forwarding Requirements](REFINE_FORWARDING_REQUIREMENTS.md) | Pattern template (4-layer structure) and prerequisite — REQ-RF-001..006 provide the `refine_suggestions` data this doc's bridge consumes |
| [Artisan Functional Requirements](design/artisan/ARTISAN_REQUIREMENTS.md) | AR-120..128 (DESIGN phase), AR-900..908 (Mottainai compliance), AR-1000..1024 (project-centric context) |
| [Plan Ingestion Requirements](PLAN_INGESTION_REQUIREMENTS.md) | REQ-PI-001 (seed completeness) depends on REQ-PD-003 to populate `requirements_text` |
| [`artisan-pipeline.contract.yaml`](../src/startd8/contractors/contracts/artisan-pipeline.contract.yaml) | Updated by REQ-PD-016 with foundation enrichment declarations |
| [`context_seed_handlers.py`](../src/startd8/contractors/context_seed_handlers.py) | Primary modification target — `DesignPhaseHandler` and `PlanPhaseHandler` |
| [`plan_ingestion_workflow.py`](../src/startd8/workflows/builtin/plan_ingestion_workflow.py) | REQ-PD-003 modification target — `_phase_emit()` |
| [`design_documentation.py`](../src/startd8/contractors/artisan_phases/design_documentation.py) | REQ-PD-005, REQ-PD-006 modification target — `FeatureContext`, system prompt, refine prompt |
| [`plan_ingestion_models.py`](../src/startd8/workflows/builtin/plan_ingestion_models.py) | `ComplexityScore` and `ArtisanContextSeed` — data source for REQ-PD-002 |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-23 | Initial version: 16 requirements across 4 layers, 3 propagation chains, 5 traceability matrices, implementation priority. |
