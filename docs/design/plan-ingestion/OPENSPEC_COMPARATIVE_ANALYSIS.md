# OpenSpec Comparative Analysis

**Author:** agent:claude-code
**Date:** 2026-03-17
**Purpose:** Deep structural comparison of [OpenSpec](https://github.com/Fission-AI/OpenSpec) spec-driven workflow against StartD8 plan ingestion + Prime Contractor, identifying patterns to adopt vs. reject

---

## OpenSpec Overview

OpenSpec is a lightweight spec-driven development framework (MIT, TypeScript) that structures AI-assisted development into four artifacts per change:

```
openspec/changes/{change-name}/
├── proposal.md          # Why + scope + approach
├── specs/               # Requirements (WHEN/THEN scenarios, delta specs)
│   └── {domain}/spec.md
├── design.md            # Goals, non-goals, decisions, risks
└── tasks.md             # Hierarchical implementation checklist
```

**Core philosophy:** "Fluid, not rigid" — artifacts can be updated at any time without phase gates. Commands are actions (propose, apply, archive), not stages.

**Key workflow:** Proposal → Specs → Design → Tasks → Implementation → Verify → Archive

**Schema system:** `schemas/spec-driven/schema.yaml` defines artifact dependencies:
- proposal (root — no dependencies)
- specs (requires: proposal)
- design (requires: proposal)
- tasks (requires: specs AND design)

Templates in `schemas/spec-driven/templates/` provide structural guidance for each artifact type.

---

## Stage-by-Stage Comparison

### What Each System Captures

| Concept | OpenSpec | StartD8 Plan Ingestion | Gap |
|---------|---------|----------------------|-----|
| **Intent (why)** | Explicit: proposal.md "Why" section | Implicit: buried in plan prose | CLOSED (REQ-OI-003: intent field) |
| **Scope boundaries** | Explicit: proposal "What Changes" + "Impact" sections | Partial: `negative_scope` per feature | CLOSED (REQ-OI-003: scope_boundary) |
| **Approach** | Explicit: proposal section | Implicit: LLM infers from plan | CLOSED (REQ-OI-003: approach field) |
| **Requirements** | Structured: WHEN/THEN scenarios per domain | Semi-structured: `api_signatures` list, `requirements_text` | Acceptable gap — LLM extracts requirements from plan prose |
| **Design decisions** | Explicit: design.md with Goals/Non-Goals/Decisions/Risks | Lost: REFINE produces review but it's discarded before code gen | CLOSED (REQ-OI-004: design_snapshot) |
| **Task decomposition** | Manual: hierarchical checklist (`- [ ] 1.1 Task`) | Automated: LLM extracts features → task derivation | StartD8 is stronger here |
| **Dependencies** | Manual: human-authored, reviewed | LLM-generated: unreliable, can contain cycles | CLOSED (REQ-OI-002: acyclicity gate) |
| **Mode (create vs edit)** | Explicit: delta specs declare ADDED vs MODIFIED | Implicit: discovered at generation time from file existence | CLOSED (REQ-OI-001: mode field) |
| **Requirement tracing** | Bidirectional: capability_id → specs → tasks | One-way: requirement_ids → acceptance_obligations text | CLOSED (REQ-OI-005: capability_coverage_map) |

### Data Loss Between Stages

| Lost Between | What Gets Lost | OpenSpec Equivalent | Addressed? |
|---|---|---|---|
| PARSE → ASSESS | Intent, scope boundaries, approach rationale | Proposal artifact persists through all phases | YES (OI-003) |
| ASSESS → TRANSFORM | 7 dimensional scores, routing reasoning | N/A (OpenSpec has no complexity routing) | Not applicable |
| TRANSFORM → REFINE | Feature-level acceptance criteria become comments | Specs persist independently of design | Partial — api_signatures forwarded but not as structured gates |
| REFINE → EMIT | Design decisions, review rationale | Design artifact persists | YES (OI-004) |
| EMIT → Code Gen | design_doc_sections forwarded but design document is not | Design referenced by tasks | YES (OI-004: design_document in gen_context) |

### Implicit vs Explicit

| Concept | StartD8 Before | StartD8 After | OpenSpec |
|---|---|---|---|
| Proposal | Implicit (flat prose) | Explicit (intent, scope_boundary, approach) | Explicit (structured proposal.md) |
| Acceptance criteria | Implicit (api_signatures as list) | Same | Explicit (WHEN/THEN scenarios) |
| Design | Implicit (lost after REFINE) | Explicit (design_snapshot in seed) | Explicit (design.md artifact) |
| Scope boundaries | Partial (negative_scope per feature) | Explicit (plan-level scope_boundary, P1 in spec prompt) | Explicit (proposal "Does NOT" section) |
| Create vs edit | Implicit (file existence check at gen time) | Explicit (mode field in PARSE) | Explicit (ADDED/MODIFIED delta specs) |
| Requirement coverage | Implicit (scan all tasks) | Explicit (capability_coverage_map) | Explicit (capability_id kebab-case linking) |

---

## Patterns Adopted (Essential Complexity)

### 1. Mode Declaration (REQ-OI-001)

**OpenSpec pattern:** Delta specs classify each requirement as ADDED (create), MODIFIED (edit), or REMOVED (delete) at spec time — before any code is written.

**StartD8 adoption:** Add `mode` field to ParsedFeature, extracted during PARSE from plan language cues ("implement" → create, "update" → edit). Threaded via QP-1 to task context. Reaches spec builder and drafter before prompt assembly.

**Why essential:** Leg 13 #45 documented 15% of merge failures from wrong-mode prompts. The signal existed in the plan text but arrived too late.

### 2. Acyclicity Gate (REQ-OI-002)

**OpenSpec pattern:** Proposal dependencies are human-authored and reviewed — cycles are caught by the author. No automated cycle detection needed because the source is reliable.

**StartD8 adoption:** LLM-generated dependency graphs are NOT reliable. Add iterative DFS cycle detection after PARSE, before ASSESS. Break back-edges and continue rather than failing.

**Why essential:** contextcore-demo-retail: 0/17 features processed, $0.19 wasted per run. Cycle detection existed at runtime (FeatureQueue) but ran after 3 LLM phases had already executed.

### 3. Proposal Capture (REQ-OI-003)

**OpenSpec pattern:** Proposal is a first-class artifact with structured sections (Why / What Changes / Capabilities / Impact). Persists through all phases.

**StartD8 adoption:** Extract intent, scope_boundary, approach from the same PARSE LLM call (zero cost). Forward scope_boundary to spec builder as P1 section.

**Why essential:** Leg 11 #40 and Leg 13 #45 — without structured scope, the LLM adds features outside scope. ASSESS can't distinguish plan ambiguity from extraction errors.

### 4. Design Snapshot (REQ-OI-004)

**OpenSpec pattern:** Design is produced BEFORE tasks, with explicit Design → Task references. Decisions, goals, non-goals, and risks are captured and accessible during implementation.

**StartD8 adoption:** Capture last REFINE round output as design_snapshot. Store in seed. Lift to gen_context["design_document"]. Triggers spec_from_design template auto-selection.

**Why essential:** Leg 13 #48 — PhaseResult output vs metadata routing confusion. Design decisions from architectural review were extracted as binary ACCEPT/REJECT but the rationale and guidance were discarded before code generation.

### 5. Capability Coverage Map (REQ-OI-005)

**OpenSpec pattern:** Kebab-case capability IDs link proposal → specs → tasks bidirectionally. Coverage is auditable at any time.

**StartD8 adoption:** Invert existing per-task requirement_ids into a coverage map at EMIT time. Zero new data — just a different view.

**Why essential:** ContextCore REQ-8 (cross-repo dashboard alignment) requires knowing which tasks implement which requirements. The data existed but had no reverse index.

---

## Patterns Rejected (Accidental Complexity)

### 1. Delta Specs (ADDED/MODIFIED/REMOVED)

**OpenSpec need:** Specs live in git alongside code. Multiple changes may target the same spec file. Delta isolation prevents merge conflicts.

**Why accidental for StartD8:** Seeds are generated fresh per pipeline run. There's no "merge to main" step — each run produces a complete seed. The mode field (OI-001) captures the create/edit distinction without the delta spec ceremony.

### 2. Change Isolation Directories

**OpenSpec need:** Each change gets its own `openspec/changes/{name}/` directory with independent artifacts. Enables parallel work streams.

**Why accidental for StartD8:** The ContextSeed model already isolates per-run state in `.startd8/state/` with checksums and resume caching. Adding filesystem directory conventions would duplicate this.

### 3. Multi-Artifact File Structure

**OpenSpec need:** Separate files (proposal.md, specs/, design.md, tasks.md) enable human review at each stage. Markdown is the collaboration format.

**Why accidental for StartD8:** The pipeline is automated — there's no human review step between PARSE and EMIT. Structured data in JSON (the seed) is superior to markdown for machine consumption. Writing intermediate markdown files would add I/O cost with no consumer.

### 4. Verification Step

**OpenSpec need:** `/opsx:verify` validates completeness, correctness, and coherence before archiving. Catches human-AI misalignment.

**Why accidental for StartD8:** The REFINE phase (1-5 round architectural review) already performs multi-dimensional validation. Post-generation checkpoints (syntax, lint, stubs, imports) validate correctness. Adding another verification layer would be redundant.

### 5. Schema System (schema.yaml + templates/)

**OpenSpec need:** Custom schemas let teams define their own artifact types and dependency graphs. Enterprise flexibility.

**Why accidental for StartD8:** The pipeline has a fixed 6-phase structure (PARSE → ASSESS → TRANSFORM → REFINE → EMIT → code gen). Artifact types and dependencies are managed by the seed schema and ContextSeed dataclass, not by user-configurable templates.

---

## Assumptions That Break for Non-Trivial Projects

| Assumption | How OpenSpec Handles It | How StartD8 Handles It | Status |
|---|---|---|---|
| Single file per feature | Not applicable (human decomposition) | Enforced via max_files=1 gate; auto-split | Existing — works for both |
| Dependencies are acyclic | Human-authored → reliable | LLM-generated → unreliable | FIXED (OI-002) |
| Design survives to implementation | Design artifact is a file on disk | Was lost between REFINE and gen | FIXED (OI-004) |
| Scope is respected | Proposal has explicit scope section | Was implicit in plan prose | FIXED (OI-003) |
| Mode is known before generation | Delta specs declare ADDED/MODIFIED | Was discovered from filesystem | FIXED (OI-001) |
| Requirements are traceable | Capability IDs link artifacts | One-way text injection | FIXED (OI-005) |

---

## Architectural Comparison

```
OpenSpec (Human-AI Collaboration Layer):
  proposal.md → specs/*.md → design.md → tasks.md → code → verify → archive
       ↑             ↑            ↑           ↑
   human writes  human reviews  human decides  human tracks

StartD8 (Automated Pipeline Layer):
  plan.md → PARSE → ASSESS → TRANSFORM → REFINE → EMIT → seed → Prime Contractor → code
       ↑      ↑                                      ↑                    ↑
   human    LLM                                    LLM               LLM + checkpoints
```

**Key insight:** OpenSpec and StartD8 operate at different layers. OpenSpec structures the human↔AI conversation (what to build). StartD8 automates the build pipeline (how to generate code from a spec). They're complementary — OpenSpec artifacts can feed StartD8's plan ingestion as an input format (see OPENSPEC_ADAPTER_REQUIREMENTS.md).

---

## Implementation Summary

| Improvement | LOC | LLM Calls | Files Modified |
|---|---|---|---|
| REQ-OI-001 (Mode) | ~10 | 0 | 4 files |
| REQ-OI-002 (Acyclicity) | ~35 | 0 | 1 file |
| REQ-OI-003 (Proposal) | ~15 | 0 | 4 files |
| REQ-OI-004 (Design Snapshot) | ~15 | 0 | 4 files |
| REQ-OI-005 (Coverage Map) | ~10 | 0 | 2 files |
| **Total** | **~85** | **0** | **6 unique files** |

All improvements extend existing extraction and threading mechanisms. Zero new pipeline phases, zero new LLM calls, zero new dependencies.
