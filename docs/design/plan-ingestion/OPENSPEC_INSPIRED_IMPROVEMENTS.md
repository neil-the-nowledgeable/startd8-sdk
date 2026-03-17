# OpenSpec-Inspired Plan Ingestion Improvements

**Author:** agent:claude-code
**Date:** 2026-03-17
**Status:** Draft
**Source:** Patterns reverse-engineered from [OpenSpec](https://github.com/Fission-AI/OpenSpec) spec-driven workflow
**Principle:** Only essential complexity — each requirement addresses a documented failure mode

---

## Context

Analysis of OpenSpec's spec-driven workflow against StartD8's plan ingestion pipeline
revealed five structural gaps where information is either lost between stages or left
implicit when it should be explicit. Each gap maps to at least one documented incident
in the lessons learned corpus.

### Design Principle

OpenSpec enforces **deliberate information flow** — each artifact explicitly feeds the
next with typed relationships. StartD8 captures the right *types* of data but loses
the *relationships* between stages. These requirements close that gap without adopting
OpenSpec's git-based change isolation, delta spec format, or multi-artifact directory
structure (all of which would be accidental complexity in StartD8's pipeline model).

### What We're NOT Doing

- No OpenSpec npm dependency or directory convention
- No new pipeline phases (all changes fit within existing PARSE/ASSESS/TRANSFORM/REFINE/EMIT)
- No delta spec format (StartD8 generates fresh per run; no merge step)
- No change isolation directories (ContextSeed already handles multi-run state)

---

## Requirements (Priority Order)

### REQ-OI-001: Mode Declaration (Create vs Edit)

**Priority:** HIGH
**Cost:** ~10 LOC in ParsedFeature + PARSE prompt
**Addresses:** Leg 13 #45 (three-layer signal mismatch — mode derived too late from filesystem)

#### Problem

The pipeline discovers create vs edit mode at code generation time by checking whether
the target file exists on disk. By then, the spec and draft prompts have already been
assembled without mode-appropriate instructions. The LLM generates "create" code for
files that need surgical edits, or "edit" code for files that don't exist yet.

OpenSpec solves this with delta specs: ADDED requirements are create-mode, MODIFIED
requirements are edit-mode — declared upfront in the spec, not discovered at gen time.

#### Requirements

**REQ-OI-001a:** `ParsedFeature` MUST include a `mode` field with values
`"create"` or `"edit"`.

**REQ-OI-001b:** The PARSE prompt MUST instruct the LLM to classify each feature's
mode based on plan language:
- `"create"` — plan says "implement", "add", "new", "create", or target file does
  not exist in the mentioned_files context
- `"edit"` — plan says "update", "modify", "change", "refactor", "fix", or target
  file is described as existing

**REQ-OI-001c:** The `mode` field MUST be added to `_CONTEXT_THREADABLE_FIELDS` so
it flows automatically into per-task context via QP-1.

**REQ-OI-001d:** `SeedTask` MUST include a `mode` field, extracted from
`context.get("mode", "create")` in `from_seed_entry()`.

**REQ-OI-001e:** The `_build_generation_context()` method in `prime_contractor.py`
MUST forward `mode` into `gen_context` so that `spec_builder.py` and `drafter.py`
can use it for prompt steering.

#### Acceptance Criteria

- PARSE response JSON includes `"mode": "create"` or `"mode": "edit"` per feature
- A feature targeting `src/existing_service/handler.go` with plan text "update the
  handler to add retry logic" is classified as `"edit"`
- A feature targeting `src/new_service/main.go` with plan text "implement the gRPC
  server" is classified as `"create"`
- Mode is visible in the enriched seed JSON at `tasks[].config.context.mode`

---

### REQ-OI-002: Acyclicity Gate Post-ASSESS

**Priority:** HIGH
**Cost:** ~10 LOC
**Addresses:** Circular dependency deadlock (contextcore-demo-retail 0/17 features;
Leg 13 queue cycle detection)

#### Problem

The PARSE LLM generates a `dependency_graph` which may contain cycles (e.g. A→B, B→A).
These cycles are not detected until runtime in `FeatureQueue.get_next_feature()`, by
which time ASSESS, TRANSFORM, and REFINE have already consumed LLM calls. The queue
then deadlocks silently — all features report as "blocked".

OpenSpec avoids this because human-authored proposals have explicit, reviewed dependency
declarations. In StartD8, the LLM generates dependencies without validation.

#### Requirements

**REQ-OI-002a:** After `_phase_parse()` returns a `ParsedPlan`, the pipeline MUST
validate that `dependency_graph` is acyclic before proceeding to ASSESS.

**REQ-OI-002b:** Cycle detection MUST use iterative DFS (not recursive, to avoid
stack overflow on large graphs). The algorithm already exists in
`FeatureQueue._find_cycles()` — reuse it.

**REQ-OI-002c:** When cycles are detected, the pipeline MUST:
1. Log a WARNING with the specific cycle(s) found
2. Break cycles by removing back-edges (same strategy as `_detect_and_break_cycles()`)
3. Continue with the repaired graph (do NOT fail the pipeline)

**REQ-OI-002d:** Cycle detection and repair MUST run before any LLM calls beyond
PARSE (i.e., before ASSESS).

#### Acceptance Criteria

- A plan with features F-001→F-002→F-001 logs a cycle warning and breaks the back-edge
- The repaired dependency_graph is acyclic (verifiable via topological sort)
- Pipeline continues to ASSESS with the repaired graph
- No additional LLM calls consumed by cycle detection

---

### REQ-OI-003: Proposal Capture (Intent / Scope / Approach)

**Priority:** HIGH
**Cost:** ~15 LOC in PARSE prompt + ParsedPlan model
**Addresses:** Leg 13 #45 (mode classification from filesystem, not plan intent);
Leg 11 #40 (result-based module contract contamination from plan misinterpretation)

#### Problem

StartD8 treats the plan as flat prose — the PARSE phase extracts features but not the
plan's *intent* (why), *scope boundaries* (what's out), or *approach* (how). Without
these, ASSESS can't distinguish "the LLM misread the plan" from "the plan is genuinely
ambiguous", and code generation has no high-level framing to validate against.

OpenSpec captures this in a structured proposal artifact (Why / What Changes /
Capabilities / Impact). StartD8 can extract the same structure from the existing PARSE
response — no additional LLM call needed.

#### Requirements

**REQ-OI-003a:** `ParsedPlan` MUST include three new optional fields:
- `intent: str` — why this plan exists (1-2 sentences)
- `scope_boundary: str` — what is explicitly out of scope
- `approach: str` — high-level technical approach

**REQ-OI-003b:** The PARSE prompt MUST request these fields in the top-level JSON
response (alongside existing `title`, `goals`, `features`):
```json
{
  "title": "...",
  "intent": "Why this plan exists — the problem being solved",
  "scope_boundary": "What is explicitly OUT of scope or excluded",
  "approach": "High-level technical strategy (1-2 sentences)",
  "goals": [...],
  "features": [...]
}
```

**REQ-OI-003c:** `intent` and `scope_boundary` MUST be forwarded to the ContextSeed
as top-level fields in `plan` metadata, so they are available to the Prime Contractor's
spec builder.

**REQ-OI-003d:** The spec builder SHOULD include `scope_boundary` as a P1 section
in the spec prompt when present, so the LLM knows what NOT to implement.

#### Acceptance Criteria

- PARSE response includes `intent`, `scope_boundary`, `approach` fields
- A plan that says "This plan covers the Go services only. Python services are
  handled separately." produces `scope_boundary` containing "Python services"
- `scope_boundary` appears in the spec prompt under "## Scope Boundary"
- Missing fields default to empty string (backward compatible with existing plans)

---

### REQ-OI-004: Design Snapshot at REFINE Boundary

**Priority:** MEDIUM
**Cost:** ~30 LOC
**Addresses:** Leg 13 #48 (PhaseResult output vs metadata routing — design decisions
lost between REFINE and code generation)

#### Problem

The REFINE phase produces architectural review feedback (which areas were flagged,
what design guidance was offered). This feedback is extracted as triage decisions
(ACCEPT/REJECT) and injected into the seed as `design_calibration`. But the actual
*design rationale* — goals, non-goals, decisions, risks identified during review — is
discarded. The code generator sees task descriptions but not the design context that
was validated during review.

OpenSpec makes design a first-class artifact produced BEFORE tasks, with explicit
"Design → Task" references. StartD8 can approximate this by capturing a design
snapshot at the REFINE boundary and forwarding it through the seed.

#### Requirements

**REQ-OI-004a:** At the end of `_phase_refine()`, the pipeline MUST capture the
review output as a `design_snapshot` string (the architectural review document
produced by the final review round).

**REQ-OI-004b:** The `design_snapshot` MUST be stored in the ContextSeed under
`plan.design_snapshot` (alongside existing `plan.title`, `plan.goals`).

**REQ-OI-004c:** The Prime Contractor's `_build_generation_context()` MUST forward
`design_snapshot` into `gen_context["design_document"]` when present.

**REQ-OI-004d:** The spec builder MUST include `design_document` as a P2 section
in the spec prompt. (This path already exists for Artisan — `spec_from_design`
template — but is not wired for Prime.)

#### Acceptance Criteria

- After REFINE completes, the seed JSON contains `plan.design_snapshot` with the
  review document text
- The Prime Contractor's spec prompt includes a "## Design Document" section when
  `design_snapshot` is available
- Code generation can reference design decisions (e.g., "as specified in the design,
  use gorilla/mux for HTTP routing")
- When REFINE is skipped (`skip_arc_review=True`), `design_snapshot` is None (no error)

---

### REQ-OI-005: Capability Coverage Map

**Priority:** MEDIUM
**Cost:** ~20 LOC
**Addresses:** ContextCore cross-repo alignment (REQ-8); requirement drift across
multi-run batches

#### Problem

StartD8 has one-way requirement tracing: `requirement_ids` → `acceptance_obligations`
(injected as comment text into task descriptions). There is no reverse mapping: given
a requirement ID, you cannot query which tasks implement it, whether it's fully covered,
or which features it spans.

OpenSpec uses kebab-case capability IDs to link proposals → specs → tasks
bidirectionally. StartD8 can build an equivalent coverage map at EMIT time from
the data already present in the seed.

#### Requirements

**REQ-OI-005a:** The ContextSeed MUST include a `capability_coverage_map` field:
```python
capability_coverage_map: Optional[Dict[str, List[str]]] = None
# Maps requirement_id → list of task_ids that implement it
```

**REQ-OI-005b:** The EMIT phase MUST populate `capability_coverage_map` by inverting
the per-task `requirement_ids` field:
```python
coverage_map = {}
for task in tasks:
    for req_id in task.config.context.get("requirement_ids", []):
        coverage_map.setdefault(req_id, []).append(task.task_id)
```

**REQ-OI-005c:** The batch postmortem SHOULD report coverage gaps: requirements
that appear in the plan but have zero implementing tasks.

**REQ-OI-005d:** The `capability_coverage_map` MUST be included in the seed JSON
output so downstream tools (ContextCore dashboards, compliance audits) can consume it.

#### Acceptance Criteria

- Seed JSON contains `capability_coverage_map` mapping requirement IDs to task IDs
- A requirement referenced by 3 features appears with 3 task IDs in the map
- A requirement with zero implementing tasks is reported as a coverage gap in the
  postmortem
- The map is empty (not None) when no requirements are mapped (backward compatible)

---

## Implementation Order

| Phase | Requirement | Files to Modify | LLM Calls Added |
|-------|-------------|-----------------|-----------------|
| 1 | REQ-OI-001 (Mode) | plan_ingestion_models.py, plan_ingestion_workflow.py, seeds/models.py | 0 (extends PARSE) |
| 2 | REQ-OI-002 (Acyclicity) | plan_ingestion_workflow.py | 0 |
| 3 | REQ-OI-003 (Proposal) | plan_ingestion_models.py, plan_ingestion_workflow.py, seeds/models.py, spec_builder.py | 0 (extends PARSE) |
| 4 | REQ-OI-004 (Design Snapshot) | plan_ingestion_workflow.py, seeds/models.py, prime_contractor.py | 0 |
| 5 | REQ-OI-005 (Coverage Map) | seeds/models.py, plan_ingestion_workflow.py | 0 |

**Total: 0 additional LLM calls. ~85 LOC across 5 files.**

---

## Traceability

| Requirement | Lessons Learned Reference | OpenSpec Pattern |
|-------------|--------------------------|------------------|
| REQ-OI-001 | Leg 13 #45, Leg 10 #36 | Delta specs: ADDED vs MODIFIED |
| REQ-OI-002 | Leg 13 circular dep deadlock | Proposal: explicit reviewed dependencies |
| REQ-OI-003 | Leg 13 #45, Leg 11 #40 | Proposal: Why / What Changes / Capabilities |
| REQ-OI-004 | Leg 13 #48 | Design artifact: Goals / Non-Goals / Decisions |
| REQ-OI-005 | ContextCore REQ-8 | Capability → Requirement kebab-case mapping |
