# Context Correctness by Design

**Status:** Active design document
**Date:** 2026-02-23
**Author:** Force Multiplier Labs
**Confidence:** 0.88
**Companion:** [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)

> *"The wave/lane system prevents execution collisions but only design-time
> awareness can prevent design collisions. Two tasks that independently design
> incompatible changes to the same file are dead on arrival — no runtime gate
> can undo that waste."*

---

## Purpose

Define the design-time complement to "Context Correctness by Construction."

Where "by Construction" ensures that context fields propagate correctly through
phase boundaries at runtime — a type-checker for service compositions — "by
Design" ensures that tasks sharing files receive enough mutual context *at
design time* to produce compatible outputs. Construction catches propagation
failures after the fact. Design prevents incompatibility before a single LLM
token is generated.

This document argues that the artisan pipeline's existing wave/lane execution
system is necessary but insufficient: it prevents **execution-time collisions**
(two tasks writing the same file concurrently) but does nothing about
**design-time collisions** (two tasks designing incompatible changes to the
same file in isolation). Closing this gap requires three capabilities: lane-aware
design ordering, cumulative full-document context for lane peers, and a
shared-file manifest.

## Audience

- Contributors implementing shared-file coordination in the artisan pipeline
- System architects evaluating the gap between design and execution parallelism
- Operators debugging incompatible designs that pass all runtime gates

---

## The Problem: Design-Time Isolation in Shared-File Scenarios

The artisan pipeline has a sophisticated execution-time concurrency model:

1. **`compute_waves()`** (`artisan_contractor.py:~861`) partitions tasks into
   dependency waves using Kahn's topological sort. Tasks in wave *N* depend
   only on tasks in waves 0..*N*−1.

2. **`compute_lanes()`** (`artisan_contractor.py:~1070`) groups tasks within
   each wave into lanes using Union-Find on shared `target_files` and
   `depends_on` edges. Tasks sharing files are placed in the same lane and
   executed sequentially within it.

These mechanisms prevent **runtime collisions** — two tasks writing the same
file concurrently. But the DESIGN phase — which creates the design documents
that IMPLEMENT follows — operates with no wave or lane awareness at all.

### The Design Loop

The DESIGN phase iterates tasks in flat input order:

```python
# context_seed_handlers.py:~2335
for idx, task in enumerate(tasks, start=1):
```

No wave grouping. No lane grouping. No awareness of which tasks share files.

### Cross-Task Context: 300-Character Summaries

The only cross-task context available during design is `prior_summaries`
(`context_seed_handlers.py:~2209`), built by truncating each prior design
document to its first line:

```python
# context_seed_handlers.py:~2537-2541
doc_text = result.design_document.raw_text
first_line = doc_text[:300].split("\n")[0]
summary = f"{task.task_id} ({task.title}): {first_line}"
prior_summaries.append(summary)
```

These summaries are injected into the design prompt as the last 5 entries:

```python
# context_seed_handlers.py:~1729-1733
if prior_design_summaries:
    additional_context["prior_designs"] = (
        "Previously designed tasks:\n"
        + "\n".join(f"- {s}" for s in prior_design_summaries[-5:])
    )
```

A 300-character first-line truncation of an 800-line design document provides
effectively zero information about the design decisions within it. When Task A
and Task B both modify `utils.py`, Task B's LLM sees a summary like:

```
PI-001 (Add health check endpoint): # Health Check Endpoint Design
```

This tells Task B nothing about what functions Task A added to `utils.py`,
what imports it expects, or what interfaces it designed.

### The Feature Context Gap

`_task_to_feature_context()` (`context_seed_handlers.py:~1635`) builds the
`FeatureContext` that drives design generation. Its signature includes no
lane-awareness parameters:

```python
@staticmethod
def _task_to_feature_context(
    task: SeedTask,
    *,
    prior_design_summaries: list[str] | None = None,
    # ... 18 other parameters, none lane-related
) -> FeatureContext:
```

There is no `lane_prior_designs` parameter (full design docs from lane peers),
no `shared_file_manifest` parameter (map of which files are contested), and no
`wave_index` parameter (this task's position in the dependency graph).

### The Cascade

The isolation produces a predictable cascade:

1. **Incompatible designs** — Task A designs `utils.py` with `class HealthChecker`.
   Task B designs `utils.py` with `class HealthMonitor`. Both are valid in
   isolation; both are incompatible when merged.

2. **Destructive implementations** — IMPLEMENT follows each design faithfully.
   Task A's generated code and Task B's generated code both write `utils.py`
   with incompatible class definitions.

3. **Edit-first gate catches the symptom** — The edit-first enforcement gate
   (REQ-EFE-020) detects the size regression when a complete-file overwrite
   replaces an existing file. But it can only reject or retry with an
   edit-focused prompt — it cannot fix the underlying design incompatibility.

4. **Wasted LLM cost** — The designs were dead on arrival. Every token spent
   on implementation, testing, and review of an incompatible design is waste.

### Code References

| Location | Current State | Gap |
|---|---|---|
| `context_seed_handlers.py:~2335` | `for idx, task in enumerate(tasks)` — flat iteration | Should be lane-by-lane, wave-sorted within lane |
| `context_seed_handlers.py:~2209` | `prior_summaries: list[str]` — 300-char first line | Should be full design docs for lane peers |
| `context_seed_handlers.py:~1635` | `_task_to_feature_context()` — no lane params | Needs `lane_prior_designs` and `shared_file_manifest` params |
| `context_seed_handlers.py:~1729-1733` | Last 5 summaries in `additional_context["prior_designs"]` | Should distinguish lane-internal (full docs) from cross-lane (summaries) |
| `artisan_contractor.py:~1070-1139` | `compute_lanes()` — called only at IMPLEMENT time | Must also be called at DESIGN time (same function, single source of truth) |
| `plan_ingestion_workflow.py:~172-197` | `_assign_wave_indices()` computes waves, does NOT compute lanes | Should include lane assignments for earlier awareness |
| `artisan-pipeline.contract.yaml:~114-150` | DESIGN phase: no lane requirements | Should declare lane assignments as advisory exit requirement |

---

## Theoretical Foundation

### Design-Time Information Flow

The problem is an instance of the **information flow** problem from
programming language theory (Denning, 1976). In the classical formulation,
information must not *leak* from high-security to low-security contexts. Here,
the formulation is inverted: information must not *fail to flow* from one
design context to another when both contexts share files.

Define a **design context** *D(t)* as the set of all design decisions made
for task *t* — class names, function signatures, import paths, interface
contracts. When two tasks *t₁* and *t₂* share a target file *f*:

- **Design coherence** requires: *D(t₂)* is compatible with *D(t₁)* with
  respect to *f*.
- **Design isolation** produces: *D(t₂)* is independent of *D(t₁)* —
  compatibility is accidental, not guaranteed.

The existing pipeline guarantees execution coherence (via `compute_lanes()`)
but only design isolation (via flat iteration with 300-char summaries).

### Monotonic Context Accumulation

Within a lane (a set of tasks sharing files), design context should accumulate
monotonically: each subsequent task's design context is a superset of the
prior tasks' design contexts with respect to shared files.

Formally, for tasks *t₁, t₂, ..., tₙ* in a lane ordered by wave index:

```
SharedContext(t₁) ⊆ SharedContext(t₂) ⊆ ... ⊆ SharedContext(tₙ)
```

where `SharedContext(tᵢ)` is the design context available to *tᵢ* about
shared files. The current pipeline violates this: `SharedContext(tᵢ)` ≈ ∅
for all *i* (the 300-char summaries provide negligible shared-file context).

### Lane Coherence Invariant

**Lane Coherence Invariant:** For any lane *L* containing tasks {*t₁, ..., tₙ*}
sharing files {*f₁, ..., fₘ*}, every task *tᵢ* (i > 1) must receive the full
design documents of all prior lane tasks {*t₁, ..., tᵢ₋₁*} as input context,
enabling the LLM to produce designs compatible with prior decisions about
shared files.

This invariant converts design coherence from an accidental property (it
happens to be compatible) to a structural property (the LLM has enough context
to *make* it compatible).

---

## Comparison: by Construction vs. by Design

| Dimension | by Construction | by Design |
|---|---|---|
| **When** | Runtime (phase boundaries) | Design time (before LLM generation) |
| **What** | Context *fields* propagate through phases | Design *decisions* propagate through shared-file tasks |
| **Mechanism** | Contract YAML + `BoundaryValidator` | Lane computation + cumulative context injection |
| **Failure mode caught** | Silent degradation of context fields | Incompatible designs for shared files |
| **Signal** | `ChainStatus`: INTACT / DEGRADED / BROKEN | Lane coherence: COHERENT / ISOLATED / CONFLICTING |
| **Cost of failure** | Subtly worse output (wrong defaults) | Wasted LLM cost on dead-on-arrival designs |
| **Existing implementation** | Layer 1 propagation contracts (62 tests) | None — this document defines the gap |
| **Scope** | All cross-phase context fields | Only tasks sharing target files (lane peers) |
| **Relationship** | Validates that context *arrived* | Ensures context was *available to produce compatible designs* |
| **Analog** | Type checker (catches type errors at boundaries) | IDE (shows type info while you write code) |

The two principles are complementary, not competing:

- **by Design** prevents the *production* of incompatible artifacts
- **by Construction** prevents the *propagation failure* of compatible artifacts

Both are needed. A pipeline with only "by Construction" catches when a field
drops at a boundary but cannot prevent two tasks from independently designing
incompatible changes to the same file. A pipeline with only "by Design"
ensures compatible designs but cannot catch when a design decision fails to
propagate from DESIGN to IMPLEMENT.

---

## The Three Pillars

### Pillar 1: Lane-Aware Design Ordering

**Principle:** Process tasks lane-by-lane, wave-sorted within each lane.

Instead of flat iteration over all tasks, the DESIGN phase should:

1. Compute lanes using the same `compute_lanes()` function used at IMPLEMENT
   time (`artisan_contractor.py:~1070`) — single source of truth.
2. Within each lane, sort tasks by `wave_index` (ascending).
3. Process lanes sequentially (or concurrently, since lanes are independent by
   definition — they share no files).
4. Within a lane, process tasks sequentially in wave order.

This ensures that when Task B designs changes to `utils.py`, Task A's design
for `utils.py` has already been completed (because A is in an earlier wave
within the same lane).

**Why wave-sorted:** Tasks in later waves may depend on tasks in earlier
waves. Processing in wave order respects the dependency graph. Within a single
wave (no inter-task dependency), the ordering within a lane is arbitrary but
deterministic (lexicographic by task_id for reproducibility).

**Why same function:** Using `compute_lanes()` at both DESIGN and IMPLEMENT
time guarantees that the lane assignments are identical. If DESIGN used a
different grouping algorithm, the coherence guarantee would not transfer to
execution.

### Pillar 2: Cumulative Full-Document Context for Lane Peers

**Principle:** Replace 300-char summaries with full design documents for
lane peers.

When designing task *tᵢ* within a lane:

- **Lane-internal context (full docs):** Provide the complete design
  documents of all prior lane tasks {*t₁, ..., tᵢ₋₁*}. These are the tasks
  sharing files with *tᵢ* — the LLM needs their full design decisions to
  produce compatible output.

- **Cross-lane context (summaries):** Continue using 300-char summaries for
  tasks in other lanes. These tasks share no files with *tᵢ*, so full
  documents would add cost without coherence benefit.

This creates a two-tier context model:

| Context Tier | Source | Content | Purpose |
|---|---|---|---|
| **Tier 1: Lane peers** | Same lane, earlier wave | Full design document text | Design coherence for shared files |
| **Tier 2: Other tasks** | Different lanes | 300-char first-line summary | General awareness (existing behavior) |

**Size guard:** Full design documents can be large (800+ lines). A token
budget should cap the total lane-peer context injected into any single design
prompt. When the budget is exceeded, prioritize the most recent lane peer
(closest in wave order) and fall back to summaries for earlier peers. Log a
warning when truncation occurs.

### Pillar 3: Shared-File Manifest

**Principle:** Build a per-task map of which files are contested and by whom.

Before design begins, compute a **shared-file manifest**: for each task, which
of its `target_files` are also targeted by other tasks, and which tasks those
are. This manifest serves three purposes:

1. **Design prompt injection:** When the LLM designs Task B's changes to
   `utils.py`, the prompt includes: "This file is also being modified by
   Task A (health check endpoint) and Task C (metrics collector). Your design
   must be compatible with theirs."

2. **Lane validation:** The manifest provides a cross-check for lane
   computation. Every file appearing in the manifest for a task should also
   appear in the lane computation. A mismatch indicates a bug.

3. **Critical path detection:** Tasks whose files appear in many other tasks'
   manifests are on the critical design path. These tasks should be designed
   first (lowest wave index within their lane) to establish the ground truth
   that other designs must follow.

---

## Application Rules

When implementing or modifying design-time coordination in the artisan pipeline:

### Rule D1: Lane Before Design

Before the DESIGN phase iterates over tasks, compute lane assignments using
`compute_lanes()`. Never process shared-file tasks in arbitrary order — the
lane ordering is the correctness guarantee.

### Rule D2: Full Docs for Lane Peers, Summaries for Others

When building the design prompt for task *tᵢ*, include full design documents
from prior lane peers and 300-char summaries from other lanes. The distinction
is load-bearing: full docs enable coherence checking, summaries provide general
awareness.

### Rule D3: Same Function, Same Assignments

Use the same `compute_lanes()` function at DESIGN time and IMPLEMENT time.
Never implement a separate lane-computation algorithm for design ordering —
divergent algorithms produce divergent lane assignments, breaking the coherence
guarantee.

### Rule D4: Manifest Before Prompt

Before injecting lane-peer context into the design prompt, consult the
shared-file manifest. The prompt should explicitly name which files are
contested and by whom, so the LLM can focus its compatibility reasoning on
the right files.

### Rule D5: Token Budget, Not Unbounded Injection

Full design documents can exceed prompt token limits. Apply a configurable
token budget for lane-peer context. When the budget is exceeded, prioritize
the most recent lane peer and fall back to summaries for earlier peers. Always
log when truncation occurs (Mottainai Rule 3: Degrade gracefully).

### Rule D6: Measure Design Coherence

When a design collision is detected downstream (by the edit-first gate, by
REVIEW, or by a human), trace it back to the DESIGN phase and record whether
the tasks were in the same lane, whether lane-peer context was available, and
whether the manifest correctly identified the shared file. This closes the
feedback loop (Mottainai Rule 6: Measure the gap).

---

## Relationship to Existing Principles

### Mottainai (もったいない)

Mottainai identifies 36 gaps where artifacts produced by earlier stages are
discarded or regenerated. "by Design" addresses a root cause upstream of many
Mottainai violations: when designs are incompatible, the entire IMPLEMENT →
INTEGRATE → TEST → REVIEW chain produces artifacts that are wasted. Preventing
design collisions eliminates a category of downstream waste.

Specific Mottainai gaps addressed:

| Gap | Description | How "by Design" Helps |
|-----|-------------|----------------------|
| Gap 17 | Reviewer verdicts discarded | Fewer review-level rejections when designs are compatible |
| Gap 19 | Design sections not serialized | Full docs forwarded to lane peers (requires serialization) |
| Gap 25 | `file_scope` not forwarded | Shared-file manifest provides a superset of file_scope data |
| Gap 26 | Downstream files re-derived | Lane computation includes downstream file analysis |

### Context Propagation (`context-propagation.md`)

Context Propagation defines how OTel trace context flows through thread
boundaries and phase transitions. "by Design" adds a new propagation dimension:
design decisions flowing between tasks within a lane. The lane-peer context
injection is a form of intra-phase context propagation that the existing
document does not address.

### ContextCore Context Contracts (`ContextCore-context-contracts.md`)

Context contracts declare what fields must flow between phases. "by Design"
extends this to declare what design context must flow between tasks within the
DESIGN phase. The shared-file manifest is analogous to a `PropagationChainSpec`
where the source is a prior lane task and the destination is the current task's
design prompt.

### Context Correctness by Construction

"by Construction" and "by Design" form a defense-in-depth pair:

```
                      DESIGN time              IMPLEMENT time           Phase boundaries
                     ┌─────────────────────┐  ┌──────────────────────┐ ┌────────────────────┐
                     │  "by Design"        │  │  compute_lanes()     │ │  "by Construction" │
                     │  ─────────────────  │  │  ──────────────────  │ │  ────────────────── │
                     │  Lane-aware ordering │  │  Sequential within   │ │  BoundaryValidator │
                     │  Full-doc context    │  │  lane execution      │ │  ChainStatus       │
                     │  Shared-file manifest│  │  Concurrent across   │ │  FieldProvenance   │
                     │                     │  │  lanes               │ │                    │
                     │  Prevents design    │  │  Prevents execution  │ │  Detects context   │
                     │  collisions          │  │  collisions          │ │  degradation       │
                     └─────────────────────┘  └──────────────────────┘ └────────────────────┘
                          Pillar 1-3              Existing                   Existing
```

### Edit-First Enforcement (REQ-EFE-020–023)

The edit-first gate detects when IMPLEMENT produces a complete-file overwrite
that regresses an existing file. This is a symptom of design collision: the
design told the LLM to write the entire file, because the design was produced
in isolation from other tasks targeting the same file. "by Design" addresses
the root cause; edit-first enforcement remains as a safety net for cases where
design coherence is imperfect.

---

## Gap Analysis: Current Wave/Lane Awareness by Phase

| Phase | Wave Awareness | Lane Awareness | Shared-File Awareness | Gap |
|-------|---------------|----------------|----------------------|-----|
| **Plan Ingestion** | Yes — `_assign_wave_indices()` computes wave_index per task | No | No | Lanes not computed at ingestion time |
| **PLAN** | Yes — `compute_waves()` called for wave_index verification | No | No | Lane computation deferred to IMPLEMENT |
| **SCAFFOLD** | No | No | Partial — `existing_target_files` computed | Only existing files, not cross-task sharing |
| **DESIGN** | No — flat `enumerate(tasks)` | No | No — 300-char summaries only | **Primary gap**: no lane ordering, no full-doc context, no manifest |
| **IMPLEMENT** | Yes — `_execute_wave_lane_mode()` uses waves | Yes — `compute_lanes()` per wave | Implicit — lane membership implies shared files | Full execution-time awareness |
| **INTEGRATE** | Inherits from IMPLEMENT | Inherits from IMPLEMENT | Inherits from IMPLEMENT | No gap at this layer |
| **TEST** | No | No | No | Tests run per-task without cross-task awareness |
| **REVIEW** | No | No | No | Reviews are per-task |

The gap is concentrated in the DESIGN phase. All other phases either have the
awareness they need (IMPLEMENT via wave-lane execution) or don't need it
(TEST and REVIEW operate on individual task outputs).

---

## Formal Requirements

See [CONTEXT_CORRECTNESS_BY_DESIGN_REQUIREMENTS.md](../design/artisan/CONTEXT_CORRECTNESS_BY_DESIGN_REQUIREMENTS.md)
for 27 formal requirements across 6 layers implementing this principle.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-23 | Initial version: principle statement, problem analysis, theoretical foundation, three pillars, application rules, gap analysis, relationship to existing principles |
