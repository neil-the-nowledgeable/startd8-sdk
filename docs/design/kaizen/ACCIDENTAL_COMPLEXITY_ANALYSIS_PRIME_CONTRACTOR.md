# Accidental Complexity Analysis: PrimeContractorWorkflow

**Date**: 2026-03-11 (fresh analysis, supersedes prior version)
**Anti-principle reference**: [`ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md`](../../design-princples/ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md)
**Scope**: Full execution path from `run_prime_workflow.py` to integrated code on disk

---

## Executive Summary

The PrimeContractorWorkflow pipeline spans **~21,900 lines across 19 files** to solve this essential problem:

> Given a list of feature descriptions and target files, generate code and merge it into the project.

Since the prior analysis, three recommendations were implemented (AC-R1 phase extraction, AC-R2 generator-native prompts, AC-R3 content-addressable cache). The `develop_feature` method shrank from 408 → 153 lines. But the total pipeline **grew by ~1,900 lines** — the new caching, observability, and post-mortem infrastructure added more code than the refactoring removed.

The pipeline now has **13 transformation layers** between "user invokes script" and "code on disk." Of these, **4 are essential**, **7 are compensatory**, and **2 are defensive**. The compensatory:essential ratio is **1.75:1** in layer count and **~2.8:1** in code volume.

**Key finding**: The prior analysis's top recommendation (AC-R1: extract `develop_feature` phases) was executed well. But three new compensatory layers were added since then (generation cache, post-mortem evaluation, element registry metrics), illustrating the **accretion pattern** — each individually justified, collectively adding cognitive load faster than the refactoring removes it.

---

## The Essential Problem

```
Input:  seed.json (feature list + target files + context)
Output: code files integrated into project, validated by checkpoint
```

**Essential transformations** (minimum viable pipeline):
1. Parse features from seed, resolve dependencies → ordered queue
2. Build generation context (description + target files + project context)
3. Generate code (LLM call)
4. Validate + integrate into project (write files, run checks)

**Essential layer count: 4**

---

## Current Pipeline: 13 Layers

### Layer Map

```
run_prime_workflow.py (779 lines)
  │
  ├─ CLI parsing, plugin wiring, seed loading, feature reset logic
  │
  ▼
FeatureQueue (538 lines)
  │
  ├─ State machine, dependency ordering, cycle detection, persistence
  │
  ▼
PrimeContractorWorkflow.__init__() → 130 lines of wiring
  │
  ├─ 23 constructor params, 25+ instance attributes, 8 lazy-init flags
  │
  ▼
PrimeContractorWorkflow.run() → process_feature() (4,410 lines total file)
  │
  ├─ Git safety, test baseline, cost/feature limits, state persistence
  │
  ▼
develop_feature() — 10 internal phases (153 lines, delegating to named methods):
  │
  ├─ Phase 1: Preflight validation                          ─── [DEFENSIVE]
  ├─ Phase 0: Copy shortcut (_try_copy_shortcut)             ─── [COMPENSATORY]
  ├─ Phase 2: Mottainai reuse (_try_mottainai_reuse)         ─── [COMPENSATORY]
  ├─ Phase 3: Context assembly (_build_generation_context)    ─── [ESSENTIAL]
  ├─ Walkthrough mode (prompt inspection)                    ─── [COMPENSATORY]
  ├─ Supplemental context threading                          ─── [ESSENTIAL (small)]
  ├─ Kaizen prompt capture (_persist_kaizen_prompts)          ─── [COMPENSATORY]
  ├─ Phase 4: Staleness detection (_check_staleness)          ─── [COMPENSATORY]
  ├─ Phase 4b: Content-addressable cache (_try_generation_cache) ─── [COMPENSATORY]
  ├─ Phase 5: Complexity routing (_route_complexity)          ─── [COMPENSATORY]
  ├─ Phase 6: Element cache assembly                         ─── [COMPENSATORY]
  ├─ Phase 7: Code generation (generator.generate)            ─── [ESSENTIAL]
  ├─ Phase 8: Quality gate (_check_quality_gate)              ─── [DEFENSIVE]
  ├─ Phase 9: Result handling (_accept_generation_result)     ─── [ESSENTIAL]
  │
  ▼
Generator (MicroPrime or LeadContractor)
  │
  ├─ MicroPrime path: engine.py (3,451 lines)
  │   ├─ Tier classification per element
  │   ├─ Template registry (TRIVIAL)
  │   ├─ Ollama generation (SIMPLE/MODERATE)
  │   ├─ Decomposition (MODERATE → sub-elements)
  │   ├─ Repair pipeline per element
  │   ├─ Body splice into skeleton
  │   ├─ Post-generation validation
  │   └─ Cloud escalation (failed elements)
  │
  ├─ LeadContractor path: lead_contractor.py (521 lines)
  │   ├─ Spec prompt → LLM
  │   ├─ Draft prompt → LLM
  │   └─ Review prompt → LLM (optional)
  │
  ▼
prime_adapter.py (2,006 lines)
  │
  ├─ Per-file processing loop
  ├─ Partial escalation (failed elements → cloud)
  ├─ Post-generation repair
  ├─ Assembly defect detection
  ├─ Structural integrity check
  ├─ Size regression guard
  └─ Fallback delegation
  │
  ▼
integrate_feature() → IntegrationEngine (1,757 lines)
  │
  ├─ Pre-integration snapshot
  ├─ Domain post-validation (advisory)
  ├─ Merge to project root
  ├─ Checkpoint validation (pytest, imports, syntax)
  ├─ Post-merge repair
  └─ Rollback on failure
  │
  ▼
process_feature() retry loop
  │
  ├─ Error-informed retry (inject failure feedback)
  ├─ Tier escalation (upgrade generator model)
  ├─ Integration attempt counter
  └─ Repair context enrichment (REQ-RPL-204)
  │
  ▼
run() post-loop
  │
  ├─ Element registry metrics (D4 + F1)
  ├─ Generation manifest write
  ├─ Tier distribution logging
  └─ Async post-mortem evaluation (NEW since prior analysis)
```

---

## Layer Classification

### Essential (4 layers)

| Layer | Code | Lines |
|-------|------|-------|
| **Context resolution** | `_build_generation_context()` + `context_resolution.py` | ~1,370 |
| **Code generation** | `generator.generate()` + LeadContractor | ~522 |
| **Checkpoint validation** | `IntegrationCheckpoint` + `checkpoint.py` | ~921 |
| **File integration** | `IntegrationEngine.integrate()` | ~1,757 |

**Essential code volume: ~4,570 lines (21%)**

### Compensatory (7 layers)

| Layer | Code | Lines | Compensates for | Justified? |
|-------|------|-------|-----------------|------------|
| **Copy detection** | `copy_detection.py` + `_try_copy_shortcut` | ~330 | Plan ingestion doesn't tag copy tasks | Marginal — could be eliminated upstream |
| **Mottainai reuse** | `_try_mottainai_reuse` + `_check_file_provenance` | ~100 | Expensive non-deterministic generation | **Yes** — real cost savings |
| **Staleness detection** | `_check_staleness` + manifest I/O | ~100 | No content-addressable cache (partially redundant with AC-R3) | **Partially redundant** |
| **Content-addressable cache** | `generation_cache.py` + `_try_generation_cache` + `_cache_generation_result` | ~230 | Repeated generation of same inputs | **Yes** — but overlaps with staleness detection |
| **Complexity routing + escalation** | `complexity/` + `_route_complexity` + `_maybe_escalate_generator` | ~1,150 | Single model can't handle all tiers | Yes for now, architectural debt long-term |
| **Kaizen prompt capture** | `_persist_kaizen_prompts` + `_build_phase_prompts` + `_write_prompt_files` + `_capture_response_files` + `_load_kaizen_config` + `_apply_kaizen_hints` | ~450 | Generator lacks native observability | **Partially addressed** by AC-R2 but parallel path still exists |
| **Element cache assembly** | `_try_element_cache_assembly` + `_assemble_from_element_cache` | ~290 | Cross-feature element duplication | **Yes** — saves real LLM calls |

**Compensatory code volume: ~2,650 lines in prime_contractor.py, triggering ~7,200 lines of downstream infrastructure**

### Defensive (2 layers)

| Layer | Code | Lines |
|-------|------|-------|
| **Preflight validation** | `pre_flight_validation()` | ~35 |
| **Quality gate** | `_check_quality_gate()` | ~40 |

---

## Sub-Pattern Analysis

### 1. Granularity Mismatch

**Status since prior analysis**: Partially resolved by file-whole eligibility gate.

**Remaining**: The MicroPrime engine (3,451 lines) + decomposer (1,029 lines) + splicer (705 lines) + repair (3,090 lines) = **8,275 lines** exist primarily to handle element-by-element generation for files above the file-whole threshold. This is the single largest code volume in the pipeline (38% of total). The file-whole path needs ~80 lines.

**The 103:1 ratio**: For each line of file-whole code, there are 103 lines of element-level infrastructure. Even accounting for the fact that element-level handles genuinely harder cases, this ratio signals that the element path has accreted its own ecosystem of compensatory layers:

```
Element path layers:
1. Tier classification per element     ─── [ESSENTIAL for element path]
2. Template registry (TRIVIAL)         ─── [COMPENSATORY] — avoids LLM call for pass-through
3. Body-only prompt construction       ─── [COMPENSATORY] — unnatural output format
4. Repair pipeline (8 steps, 1,210 lines in steps/) ─── [COMPENSATORY] — fixes generation defects
5. Body splice into skeleton           ─── [COMPENSATORY] — reassembles what decomposition broke
6. Structural verification             ─── [COMPENSATORY] — checks what splice might have broken
7. Escalation handoff                  ─── [COMPENSATORY] — recovers from local model failure
8. Assembly defect detection           ─── [COMPENSATORY] — catches what verification missed
```

Of these 8 sub-layers, only #1 (classification) addresses the essential problem. Layers 2-8 compensate for the decision to decompose below the model's natural output grain.

### 2. Validation Layer Accretion

**Current count** from input to output:

```
Input (seed.json)
  → Preflight validation                    [1]
  → Context strategy validation (8 validators in context_resolution.py) [2-9]
  → Quality gate (post-generation)          [10]
  → Per-element repair (8 steps)            [11-18]
  → Per-element structural verification     [19]
  → Assembly defect detection               [20]
  → Size regression guard                   [21]
  → Pre-merge repair                        [22]
  → Checkpoint: syntax check                [23]
  → Checkpoint: import check                [24]
  → Checkpoint: lint check                  [25]
  → Checkpoint: stub check                  [26]
  → Checkpoint: duplicate check             [27]
  → Checkpoint: import dependency alignment [28]
  → Checkpoint: test regression             [29]
  → Post-merge repair                       [30]
Output (code on disk)
```

**30 validation/repair points** between input and output. The essential validations are: AST syntax (1), import resolution (1), test regression (1) = **3 essential validations**. The remaining 27 exist to catch failures introduced by decomposition, splicing, repair, and merge operations.

**Fidelity gradient**: The same properties are checked at multiple layers with different methods:
- **Stub detection**: engine.py string check → prime_adapter.py AST check → checkpoint.py ast.walk check
- **Structural integrity**: engine.py name-only → prime_adapter.py position-aware → checkpoint.py import-dependency
- **Syntax validity**: repair/ast_validate step → engine post-gen → checkpoint pre-merge → checkpoint post-merge

### 3. Fidelity Gradient

**New instance found**: Staleness detection vs. content-addressable cache.

`_check_staleness()` (Phase 4) compares `source_checksum` against a generation manifest to decide if regeneration is needed. `_try_generation_cache()` (Phase 4b) computes `sha256(description + context_hash + model)` to look up cached results. These are **two implementations of the same concept** (skip regeneration when inputs haven't changed) at different fidelity levels:

| Property | Staleness (Phase 4) | Generation Cache (Phase 4b) |
|----------|--------------------|-----------------------------|
| Key granularity | Whole seed checksum | Per-feature (description + context + model) |
| Storage | generation-manifest.json | generation_cache/ directory |
| Invalidation | Any seed change invalidates all | Per-feature invalidation |
| File existence check | No | Yes (verifies files still on disk) |

The generation cache (AC-R3) is strictly more capable than staleness detection. **Staleness detection is now a lower-fidelity duplicate** that should be retired.

---

## The `develop_feature` Method: Before and After AC-R1

The prior analysis flagged `develop_feature` as a 408-line, 10-phase monolith. The AC-R1 refactor extracted phases into named methods, reducing it to **153 lines** — a 63% reduction and a clear win.

**Current essential:compensatory breakdown** of `develop_feature`:

| Code | Lines | Classification |
|------|-------|---------------|
| Preflight + logging | ~10 | DEFENSIVE |
| Copy shortcut delegation | ~5 | COMPENSATORY |
| Dry run / no-generator guards | ~15 | COMPENSATORY |
| Element registry logging | ~3 | COMPENSATORY |
| Mottainai reuse delegation | ~4 | COMPENSATORY |
| Context assembly delegation | ~3 | ESSENTIAL |
| Walkthrough mode | ~12 | COMPENSATORY |
| Supplemental context threading | ~3 | ESSENTIAL |
| Kaizen prompt capture | ~3 | COMPENSATORY |
| Staleness check | ~5 | COMPENSATORY |
| Generation cache check | ~5 | COMPENSATORY |
| Complexity routing | ~3 | COMPENSATORY |
| Element cache assembly | ~8 | COMPENSATORY |
| **generator.generate()** | **~20 (OTel span)** | **ESSENTIAL** |
| Kaizen post-capture | ~3 | COMPENSATORY |
| Quality gate | ~3 | DEFENSIVE |
| Result handling | ~20 | ESSENTIAL |
| Error handling | ~10 | ESSENTIAL |

**Essential: ~59 lines (39%). Compensatory: ~69 lines (45%). Defensive: ~13 lines (8%). Overhead: ~12 lines (8%).**

The method is now well-factored — the delegated methods carry the real complexity. The issue has shifted from "this method is too long" to "this method calls 12 optional preprocessing steps before the 1 essential line."

---

## The MicroPrime Sub-Pipeline: Still the Accidental Complexity Hotspot

| Component | Lines | Classification |
|-----------|-------|---------------|
| engine.py | 3,451 | Mixed: ~400 essential (file-whole), ~3,050 compensatory (element path) |
| prime_adapter.py | 2,006 | Mixed: ~300 essential (protocol bridge), ~1,700 compensatory (escalation, repair, defect detection) |
| decomposer.py | 1,029 | COMPENSATORY — exists only for element path |
| splicer.py | 705 | COMPENSATORY — reassembles what decomposition broke |
| repair/ (all files) | 3,090 | COMPENSATORY — fixes what generation broke |
| complexity/ (all files) | 1,044 | COMPENSATORY — routes to avoid element path when possible |
| **Subtotal** | **11,325** | **~700 essential, ~10,625 compensatory** |

The MicroPrime sub-pipeline is **52% of the total pipeline code** and **94% compensatory**. It exists to save $0.05-$0.15 per feature by using a local Ollama model instead of a cloud LLM. The ROI calculation:

```
Cost of MicroPrime infrastructure: ~10,625 lines of code to maintain
Cost savings: ~$0.10/feature × N features per run
Break-even (at maintenance cost of ~$50/major-fix session):
  = 500 features per major fix session to justify the maintenance
```

This is not a condemnation — the engine works and the savings are real over many runs. But the complexity cost is disproportionate, and each new MicroPrime failure mode (element-level circuit breakers, decomposition confidence scoring, escalation handoffs) adds another compensatory layer.

---

## Quantified Complexity Budget (Fresh Counts)

| Category | Files | Lines | % of Total |
|----------|-------|-------|------------|
| **Essential path** (context + generation + validation + integration) | 4 | ~4,570 | 21% |
| **MicroPrime engine** (element-level generation + repair + splice + decompose) | 6 | ~11,325 | 52% |
| **Compensatory layers** (caching, routing, retry, observability, copy detection) | 4 | ~1,670 | 8% |
| **Entry point + queue + state management** | 2 | ~1,317 | 6% |
| **Complexity classification** | 4 | ~1,044 | 5% |
| **Post-run infrastructure** (manifest, post-mortem, registry metrics) | 2 | ~350 | 2% |
| **Dead/vestigial code** (FeatureProcessor class, lines 4057-4410) | 1 | ~353 | 2% |
| **Remaining prime_contractor.py** (SeedContext, legacy sync, config, helpers) | 1 | ~1,270 | 6% |
| **Total** | **~19** | **~21,900** | **100%** |

---

## The Rube Goldberg Test Applied (Fresh)

### Layers that pass

| Layer | Verdict |
|-------|---------|
| Context resolution | **ESSENTIAL** — LLM needs context |
| Code generation | **ESSENTIAL** — this IS the problem |
| Checkpoint validation | **ESSENTIAL** — must verify correctness |
| Integration | **ESSENTIAL** — code must reach disk |
| Mottainai reuse | **COMPENSATORY, justified** — real dollar savings, simple check |
| Element cache assembly | **COMPENSATORY, justified** — same economics |
| Quality gate | **DEFENSIVE, justified** — catches real issues cheaply |
| Content-addressable cache | **COMPENSATORY, justified** — eliminates redundant LLM calls |

### Layers with accidental complexity debt

| Layer | Compensates for | Could be eliminated by | Priority |
|-------|----------------|----------------------|----------|
| **Staleness detection** (~100 lines + manifest I/O) | No content-addressable cache | **Already redundant** — AC-R3 generation cache subsumes this. Remove. | **P0 — immediate** |
| **Copy detection** (282 + 48 lines) | Plan ingestion imprecision | Plan ingestion emitting `copy_source_task_id` in seed | P1 |
| **Kaizen parallel prompt path** (~250 lines) | Generator lacks native prompts | AC-R2 is partially done — complete it, then remove `_build_phase_prompts()` fallback | P1 |
| **FeatureProcessor class** (~353 lines) | Nothing — appears to be dead code at end of file | Delete it | **P0 — immediate** |
| **Tier escalation** (~80 lines) | Local model failure | Better local models, or simplify to 2-tier (local/cloud) | P2 |
| **Complexity routing** (~1,044 lines in complexity/) | Model capability gaps | 2-tier simplification (local ≤ threshold, cloud otherwise) | P2 |
| **Element-by-element path** (~10,625 lines) | File-whole fails on large files | Models with larger reliable output windows | P3 (external dependency) |

### New since prior analysis

| Addition | Lines | Classification | Rube Goldberg test |
|----------|-------|---------------|-------------------|
| Content-addressable cache (AC-R3) | ~230 | COMPENSATORY | **Justified** — but makes staleness detection redundant |
| Post-mortem evaluation | ~15 (launch) | COMPENSATORY | Compensates for lack of real-time quality feedback — reasonable |
| Element registry metrics | ~20 | COMPENSATORY | Observability for Kaizen — reasonable but adds to post-loop code |
| OTel generation span | ~20 | ESSENTIAL | Good — native observability at the generation boundary |
| Repair context enrichment (REQ-RPL-204) | ~10 | COMPENSATORY | Compensates for opaque error messages — reasonable |

---

## Recommendations

### P0 — Immediate (eliminate dead weight)

**R1: Delete the `FeatureProcessor` class** ~~(lines 4057-4410, ~353 lines)~~ **✅ DONE**.

Deleted ~335 lines of vestigial LLM-generated code. Not in `__all__`, zero imports, never used. Also removed orphaned `import re` and unused `PipelineContextStrategy`/`create_strategy` imports exposed by the deletion.

**R2: Remove staleness detection** ~~(~100 lines)~~ **✅ DONE**.

Deleted `_check_staleness()`, `_compute_source_checksum()`, `_read_existing_manifest()` (~82 lines). Removed Phase 4 staleness check from `develop_feature`. Removed `source_checksum` from manifest, bumped schema to 1.1.0. Rewrote `test_generation_manifest.py` (343 → ~130 lines: removed 15 staleness/checksum tests, kept 7 manifest-writing tests). Updated `_DEVELOP_PATCHES` in 2 test files and walkthrough fixture.

**Net P0 reduction**: ~452 lines from `prime_contractor.py`, ~213 lines from tests.

### P1 — Short-term (reduce compensatory layers)

**R3: ~~Complete AC-R2 (generator-native prompt observability)~~ NOT FEASIBLE.**

Investigation found that MicroPrime's `generate()` does not populate `result.prompts` — it uses a template registry, not the spec/draft/review prompt pipeline. The `_build_phase_prompts()` fallback is still needed for MicroPrime-generated features. Removing it would silently lose prompt observability for ~60% of features (those routed to local generation).

**R4: ~~Emit `copy_source_task_id` in plan ingestion~~ ALREADY DONE.**

Investigation found `_enrich_copy_source()` already runs during plan ingestion enrichment (`plan_ingestion_enrichment.py`). The `copy_detection.py` runtime path is a fallback for un-enriched seeds (e.g., manually constructed seeds that skip plan ingestion). Both paths remain justified.

**R5: ~~Consolidate Mottainai + generation cache~~ KEEP BOTH.**

Investigation found the two mechanisms check genuinely different things:
- **Mottainai reuse**: Checks if the *output file* already exists and is fresh (mtime-based). Runs before context assembly. Zero cost.
- **Generation cache**: Checks if the *generation request* (description + context + model) has been seen before. Runs after context assembly. SHA-256 computation cost.

Consolidating them would mean always computing context + hash even when the file is already fresh on disk. The Mottainai check is a fast-path short-circuit that avoids the more expensive cache lookup. They are not redundant — they operate at different abstraction levels (output freshness vs input equivalence).

### P2 — Medium-term (simplify routing)

**R6: Two-tier generator simplification.**

Replace the 4-tier system (TRIVIAL/SIMPLE/MODERATE/COMPLEX) with a 2-tier system:
- **Local**: Ollama file-whole for files ≤ threshold (~100 lines)
- **Cloud**: LeadContractor for everything else

This eliminates:
- `complexity/classifier.py` (192 lines) — replace with a LOC threshold check
- `complexity/router.py` (59 lines) — replace with an if/else
- `complexity/signals.py` (579 lines) — signal extraction not needed for a size gate
- `complexity/models.py` (176 lines) — tier enum not needed
- Tier escalation logic (~80 lines) — cloud is already the top tier

**Net reduction: ~1,086 lines**, replaced by ~20 lines of threshold logic.

**Trade-off**: Loses nuance for medium-complexity tasks. The MODERATE tier (Ollama-whole attempt → decompose on failure) genuinely handles some cases well. A 2-tier system would send these to cloud, costing more but simplifying dramatically.

**Status**: Deferred — ~150+ file impact across complexity/, micro_prime/, tests/. Needs dedicated session.

**R7: ~~Raise file-whole eligibility thresholds~~ ALREADY DONE.**

Current values are already at 100 LOC / 8 elements (confirmed in `micro_prime/config_loader.py`). The prior analysis's recommendation was implemented in a previous session.

### P3 — Long-term (wait for external changes)

**R8: Retire the element-by-element path when models improve.**

The element path (10,625 lines) will become unnecessary when local models can reliably generate complete files of 200+ lines. This is an external dependency (model capability). In the meantime, R7 incrementally shrinks the element path's surface area.

**R9: Generator-native OTel observability.**

The `_gen_tracer` and `_prime_tracer` spans (AC-R7) are a good start. Extending generators to emit full OTel spans with prompt/response/cost attributes would eliminate the remaining Kaizen capture infrastructure. This is partially done — the generation span already records cost and token counts. The remaining gap is prompt/response content, which is large (tokens) and may be better suited to Loki logs than span attributes.

---

## Accidental Complexity Trend

| Metric | Prior Analysis | Current | Delta |
|--------|---------------|---------|-------|
| Total pipeline lines | ~20,000 | ~21,900 | +1,900 (+10%) |
| Essential lines | ~5,668 (28%) | ~4,570 (21%) | -1,098 (-19%) |
| Compensatory lines | ~14,332 (72%) | ~17,330 (79%) | +2,998 (+21%) |
| `develop_feature` lines | 408 | 153 | -255 (-63%) |
| Caching mechanisms | 2 | 3 | +1 |
| Validation points | ~24 (estimated) | 30 | +6 |
| Layers | 12 | 13 | +1 |
| Dead code | 0 identified | ~353 | +353 |

**The refactoring improved readability** (`develop_feature` is now clean). **But total accidental complexity grew** — new features added compensatory layers faster than the refactoring removed them.

---

## The Accretion Trap

This analysis reveals a meta-pattern not in the anti-principle document:

**The Accretion Trap**: When compensatory layers are individually justified (each saves money/time/failures), but the system never retires the layers they make redundant.

Example in this pipeline:
1. **Staleness detection** was added to skip regeneration when seed hasn't changed
2. **Content-addressable cache** (AC-R3) was added to skip regeneration per-feature
3. **Mottainai reuse** was already doing per-file provenance checks
4. All three are still active, checked sequentially: Phase 2 → Phase 4 → Phase 4b

Each was a correct decision at the time. But no one removed the weaker mechanisms when the stronger one arrived. The cost is not just 3× the code — it's the cognitive load of understanding *which* caching mechanism applies *when*, and the debugging burden when they disagree.

**Proposed addition to the anti-principle document**: When adding a new layer that subsumes an existing one, delete or deprecate the subsumed layer in the same PR.

---

## Relationship to PI-001/002

The PI-001/002 case study showed accidental complexity in the MicroPrime element path for small files. That specific instance was fixed (file-whole eligibility gate). This fresh analysis shows the same pattern at the pipeline level:

| Scope | Essential layers | Total layers | Ratio | Key compensatory burden |
|-------|-----------------|-------------|-------|------------------------|
| PI-001/002 (small file) | 2 | 18+ | 9:1 | Element decomposition + repair + splice |
| Prime contractor (full pipeline) | 4 | 13 | 3.25:1 | MicroPrime + 3 cache layers + Kaizen capture |

The pipeline's ratio is better (3.25:1 vs 9:1) but the absolute code volume is much larger (21,900 vs ~400 lines). The same principles apply at both scales.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-11 | Fresh analysis superseding prior version: 13 layers mapped (4 essential, 7 compensatory, 2 defensive), identified staleness/cache redundancy (Fidelity Gradient), dead FeatureProcessor class, accretion trap meta-pattern, 9 prioritized recommendations |
| 2026-03-11 | Implemented R1 (delete FeatureProcessor, -335 lines) + R2 (remove staleness detection, -117 lines). Research validated R3 (not feasible), R4 (already done), R5 (keep both — different abstraction levels), R7 (already done). R6 deferred (150+ file impact). Net reduction: ~665 lines code + ~213 lines tests |
