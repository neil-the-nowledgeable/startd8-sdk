# Accidental Complexity Analysis: PrimeContractorWorkflow

**Date**: 2026-03-11
**Anti-principle reference**: [`ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md`](../../design-princples/ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md)
**Scope**: Full execution path from `run_prime_workflow.py` to integrated code on disk

---

## Executive Summary

The PrimeContractorWorkflow pipeline spans **~20,000 lines across 17 files** to solve this essential problem:

> Given a list of feature descriptions and target files, generate code and merge it into the project.

The pipeline has **12 transformation layers** between "user invokes script" and "code on disk." Of these, **4 are essential** (context assembly, code generation, validation, integration) and **8 are compensatory** — they exist to recover from limitations of other layers, manage state for retry/resume, or route around failure modes that wouldn't exist if the essential path were more reliable.

This is not a crisis — the compensatory layers are individually reasonable and many have earned their keep (Mottainai reuse saves real dollars, error-informed retry genuinely improves outcomes). But the **total cognitive and maintenance cost** of the compensatory layers now exceeds the essential ones by 3:1 in code volume and 8:4 in layer count.

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

## The Actual Pipeline: 12 Layers

### Layer Map

```
run_prime_workflow.py (779 lines)
  │
  ├─ CLI parsing, plugin wiring, seed loading, feature reset logic
  │
  ▼
FeatureQueue (530 lines)
  │
  ├─ State machine, dependency ordering, cycle detection, persistence
  │
  ▼
PrimeContractorWorkflow.run() → process_feature() (4,230 lines)
  │
  ├─ Git safety, test baseline, cost/feature limits, state persistence
  │
  ▼
develop_feature() — 10 internal phases:
  │
  ├─ Phase 0: Copy detection (file_copy shortcut)           ─── [COMPENSATORY]
  ├─ Phase 1: Preflight validation                          ─── [DEFENSIVE]
  ├─ Phase 2: Context resolution (strategy pattern)         ─── [ESSENTIAL]
  ├─ Phase 3: Mottainai reuse (file provenance check)       ─── [COMPENSATORY]
  ├─ Phase 4: Staleness detection (checksum compare)        ─── [COMPENSATORY]
  ├─ Phase 5: Element cache assembly (registry lookup)      ─── [COMPENSATORY]
  ├─ Phase 6: Complexity routing (tier classification)      ─── [COMPENSATORY]
  ├─ Phase 7: Kaizen prompt capture                         ─── [COMPENSATORY]
  ├─ Phase 8: Walkthrough mode (dry run for prompts)        ─── [COMPENSATORY]
  ├─ Phase 9: Code generation (actual LLM call)             ─── [ESSENTIAL]
  ├─ Phase 10: Quality gate (score threshold)               ─── [DEFENSIVE]
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
  ├─ LeadContractor path: lead_contractor_workflow.py (1,711 lines)
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
  └─ Integration attempt counter
```

---

## Layer Classification

### Essential (4 layers) — Address the inherent problem

| Layer | Code | What it does | Why it's essential |
|-------|------|-------------|-------------------|
| **Context resolution** | `develop_feature` Phase 2, `context_resolution.py` (1,279 lines) | Build gen_context from seed data | The LLM needs context to generate code |
| **Code generation** | `develop_feature` Phase 9, generator.generate() | Produce code via LLM | This IS the problem |
| **Checkpoint validation** | `IntegrationEngine._run_checkpoint()`, `checkpoint.py` (921 lines) | Verify generated code compiles, imports resolve, tests pass | Essential quality gate — can't ship broken code |
| **File integration** | `IntegrationEngine.integrate()` (1,757 lines) | Write files to project, handle conflicts | Code must end up on disk |

**Essential code volume: ~5,668 lines (28%)**

### Compensatory (8 layers) — Exist because other layers are imperfect

| Layer | Code | What it compensates for | Rube Goldberg test |
|-------|------|------------------------|-------------------|
| **Copy detection** | Phase 0, `copy_detection.py` (282 lines) | Plan ingestion doesn't mark identical-copy tasks explicitly | Compensates for upstream (plan ingestion) imprecision |
| **Mottainai reuse** | Phase 3, provenance check (~60 lines) | LLM generation is expensive and non-deterministic | Compensates for generation cost — acceptable |
| **Staleness detection** | Phase 4, checksum compare (~40 lines) | No semantic versioning of seed context | Compensates for lack of content-addressable caching |
| **Element cache assembly** | Phase 5, registry lookup (~80 lines) | Cross-feature element duplication wastes LLM calls | Compensates for generation cost — acceptable |
| **Complexity routing** | Phase 6, `router.py` (59 lines) + classification | Single generator can't optimally handle all tiers | Compensates for model capability gaps |
| **Kaizen prompt capture** | Phase 7, `_persist_kaizen_prompts()` (~200 lines) | Post-hoc analysis needs prompt/response pairs | Compensates for lack of built-in observability |
| **Error-informed retry** | `process_feature()` retry loop (~50 lines) | First generation attempt may produce broken code | Compensates for generation unreliability |
| **Tier escalation** | `_maybe_escalate_generator()` (~40 lines) | Local/cheap model fails → try expensive model | Compensates for local model limitations |

**Compensatory code volume: ~811 lines in prime_contractor.py, but triggers ~3,350 lines of repair infrastructure**

### Defensive (2 layers) — Guard against known fragile paths

| Layer | Code | What it defends against |
|-------|------|------------------------|
| **Preflight validation** | Phase 1 (~30 lines) | Oversized features that would blow context window |
| **Quality gate** | Phase 10, CR-C1 (~50 lines) | Generator produces syntactically valid but semantically poor code |

---

## The Micro Prime Sub-Pipeline: Where Accidental Complexity Concentrates

The MicroPrime path (`engine.py` + `prime_adapter.py` + `splicer.py` + `decomposer.py` + `repair/`) is **7,700+ lines** — nearly half the total pipeline — and exists to avoid spending $0.05-$0.15 per feature on cloud LLM calls by using a local Ollama model instead.

This is the most complexity-dense section:

```
ForwardManifest
  │
  ▼
Per-file: is_file_ollama_whole_eligible?
  │
  ├─ Yes → generate entire file → validate → splice ─── [3 steps, ESSENTIAL]
  │
  └─ No → Per-element:
          │
          ├─ classify_element() → tier
          │   ├─ TRIVIAL → template registry lookup
          │   ├─ SIMPLE → build_body_prompt → Ollama → repair → splice
          │   ├─ MODERATE → Ollama-whole attempt
          │   │   ├─ Success → done
          │   │   └─ Fail → decompose → per-sub-element generation → assemble
          │   └─ COMPLEX → escalate to cloud
          │
          ├─ repair_pipeline (per element)
          │   ├─ fence_strip
          │   ├─ ast_validate
          │   ├─ indent_normalize
          │   └─ structural_reindent
          │
          ├─ splice_body_into_skeleton (per element)
          │
          ├─ verify result (per element)
          │
          └─ If failed → EscalationHandoff → cloud fallback
```

**The file-whole path** (added in run-033 to fix PI-001/002): 3 steps, ~80 lines.
**The element-by-element path**: 12+ steps per element × N elements, ~3,400 lines.

The element-by-element path is the canonical accidental complexity case from the anti-principle document. It is **still the default path for files exceeding `file_ollama_whole_max_elements` (5) or `file_ollama_whole_max_loc` (60)**.

### What makes the element path necessary?

For large files (>60 lines, >5 elements), file-whole generation genuinely degrades — the Ollama model loses coherence on long outputs. The element path is essential for these cases. The accidental complexity was applying it to *all* files, including 30-line ones.

**Current state**: The eligibility gate (`_is_file_ollama_whole_eligible`) correctly routes small files to file-whole. The element path remains for large files where it's essential.

**Remaining concern**: The 60-line / 5-element thresholds are static. A 61-line file with 3 simple elements is forced through the element path even though file-whole would likely succeed. The threshold should consider element complexity, not just count.

---

## The `develop_feature` Method: 400 Lines, 10 Phases

`develop_feature()` spans lines 3071–3479 (408 lines). Here's the essential-vs-compensatory breakdown of those lines:

| Phase | Lines | Classification | Justification |
|-------|-------|---------------|---------------|
| Phase 0: Copy detection | ~45 | COMPENSATORY | Shortcut for a pattern plan ingestion should handle |
| Dry run check | ~10 | COMPENSATORY | Testing infrastructure |
| ER-012: Registry logging | ~25 | COMPENSATORY | Observability for cache hit debugging |
| Mottainai reuse check | ~30 | COMPENSATORY | Avoids re-generation — acceptable, saves money |
| Phase 2: Context assembly | ~80 | ESSENTIAL | The LLM needs context |
| Validation flag threading | ~10 | ESSENTIAL (small) | Configures downstream validation |
| Service metadata logging | ~8 | COMPENSATORY | Observability |
| Existing file population | ~5 | ESSENTIAL | Edit tasks need current file contents |
| Manifest/skeleton threading | ~10 | ESSENTIAL | MicroPrime needs these |
| Design doc threading | ~5 | ESSENTIAL | Context enrichment |
| Walkthrough mode | ~12 | COMPENSATORY | Prompt inspection without LLM calls |
| Reference impl threading | ~8 | COMPENSATORY | Copy-and-modify optimization |
| Kaizen hint injection | ~3 | COMPENSATORY | Cross-run learning |
| Kaizen prompt capture | ~3 | COMPENSATORY | Post-hoc analysis |
| Phase 4: Staleness check | ~5 | COMPENSATORY | Cache management |
| Phase 6: Complexity routing | ~35 | COMPENSATORY | Model selection optimization |
| Element cache assembly | ~12 | COMPENSATORY | Cross-feature element reuse |
| **Phase 9: generator.generate()** | **~1** | **ESSENTIAL** | **The actual work** |
| Phase 10: Quality gate | ~20 | DEFENSIVE | Catches low-quality generation |
| Result handling | ~30 | ESSENTIAL | Persist result, update state |

**Essential: ~150 lines (37%). Compensatory: ~230 lines (56%). Defensive: ~28 lines (7%).**

The single essential line — `result = generator.generate(task=..., context=..., target_files=...)` — is surrounded by 407 lines of context assembly, caching, routing, observability, and error handling.

---

## The Rube Goldberg Test Applied

### Layers that pass

| Layer | "Does this solve the problem or compensate for another layer?" |
|-------|--------------------------------------------------------------|
| Context resolution | **Solves the problem** — LLM needs context |
| Code generation | **Solves the problem** — this IS the problem |
| Checkpoint validation | **Solves the problem** — must verify correctness |
| Integration | **Solves the problem** — code must reach disk |
| Mottainai reuse | **Compensatory but justified** — $0.05-$0.50 saved per cache hit, simple check |
| Element cache | **Compensatory but justified** — same economics as Mottainai |
| Quality gate | **Defensive but justified** — catches real quality issues cheaply |

### Layers with accidental complexity debt

| Layer | Compensates for | Could be eliminated by |
|-------|----------------|----------------------|
| **Copy detection** (282 lines) | Plan ingestion doesn't tag copy tasks | Plan ingestion emitting `copy_source_task_id` in the seed |
| **Complexity routing** (59 + ~35 lines) | Single model can't handle all tiers | A model that handles all tiers (or a simpler 2-tier split: local vs cloud) |
| **Tier escalation** (~40 lines) | Local model failure | Better local model, or always using cloud |
| **Error-informed retry** (~50 lines) | First-attempt generation failure | More reliable generation (better prompts, better models) |
| **Staleness detection** (~45 lines) | No content-addressable generation cache | Content-addressable cache keyed on (description_hash, context_hash) |
| **Kaizen prompt capture** (~200 lines) | Lack of built-in prompt observability | OTel-native prompt/response capture in the generator itself |
| **Element-by-element path** (~3,400 lines) | File-whole fails on large files | Models with larger reliable output windows |

### The big one: Kaizen infrastructure

**~200 lines** in `prime_contractor.py` + separate persistence logic for capturing prompts, responses, and hints. This exists because the generator doesn't natively emit its prompts as OTel spans. If `LeadContractorCodeGenerator.generate()` emitted structured `{prompt, response, cost, model}` telemetry, the Kaizen capture layer would be unnecessary — the data would flow through standard observability infrastructure.

**This is classic Layer Accretion**: the generator doesn't provide observability → the workflow builds its own observability → the workflow's observability needs its own config (`--kaizen-config`) → the config needs its own injection logic → the injection needs its own serialization guards (REQ-KZ-BUG-004).

---

## Quantified Complexity Budget

| Category | Files | Lines | % of Total |
|----------|-------|-------|------------|
| **Essential path** (context + generation + validation + integration) | 5 | ~5,668 | 28% |
| **MicroPrime engine** (element-level generation + repair + splice) | 5 | ~7,700 | 38% |
| **Compensatory layers** (caching, routing, retry, observability) | 4 | ~2,800 | 14% |
| **Entry point + queue + state management** | 2 | ~1,309 | 7% |
| **Supporting infrastructure** (repair, diagnostics, staging, checkpoint) | 4 | ~2,350 | 12% |
| **Total** | **17** | **~20,000** | **100%** |

The essential problem (generate code from description, validate, integrate) requires ~5,700 lines.
The remaining ~14,300 lines exist to:
- Handle the case where the cheap model fails (MicroPrime element path + repair + escalation)
- Avoid re-doing expensive work (Mottainai, staleness, element cache)
- Route to the right model (complexity routing + tier escalation)
- Observe what happened (Kaizen capture)
- Recover from integration failures (retry + error feedback)

---

## Recommendations

### Immediate (reduce cognitive load, no behavior change)

1. **Extract `develop_feature` phases into named methods.** The 10-phase 400-line method is the hardest thing to read in the codebase. Each phase is already delimited by comments — make them callable units: `_try_copy_shortcut()`, `_try_mottainai_reuse()`, `_try_staleness_cache()`, `_try_element_cache()`, `_route_complexity()`, `_build_generation_context()`, `_generate_code()`. The method becomes a 30-line orchestrator calling 10 named phases.

2. **Move Kaizen prompt capture into the generator protocol.** Define `generate()` → `GenerationResult` with optional `prompts: dict[str, str]` and `responses: dict[str, str]` fields. Generators that support observability populate these. The workflow just persists `result.prompts` — no more parallel prompt-building logic.

### Medium-term (reduce accidental complexity)

3. **Content-addressable generation cache.** Key: `sha256(description + context_hash + model)`. Value: `GenerationResult`. Eliminates staleness detection, Mottainai file-provenance checks, and element cache assembly as separate layers — they all become "is this key in the cache?"

4. **Raise file-whole eligibility thresholds.** The current 60-line / 5-element limits are conservative. Based on PI-001/002 and subsequent runs, Ollama handles files up to ~100 lines reliably. Raising the threshold routes more files away from the element path, reducing the surface area where repair/splice/escalation complexity lives.

5. **Emit `copy_source_task_id` in plan ingestion.** Eliminates `copy_detection.py` (282 lines) and Phase 0's runtime detection logic (~45 lines).

### Long-term (architectural simplification)

6. **Two-tier generator, not four-tier routing.** The current TRIVIAL/SIMPLE/MODERATE/COMPLEX tier system with per-tier generator selection is more routing complexity than the problem warrants. A simpler model: **local** (Ollama, for files ≤ threshold) and **cloud** (for everything else). The local path uses file-whole when eligible, element-by-element when not. No complexity router, no tier escalation — just a size gate.

7. **Generator-native observability.** If generators emit OTel spans with prompt/response/cost attributes, the entire Kaizen capture infrastructure (~200+ lines) collapses into "configure the OTel exporter."

---

## Relationship to PI-001/002

The PI-001/002 case study (in the anti-principle document) was a **specific instance** of the accidental complexity in the MicroPrime element path. This analysis shows it's not an isolated case — the entire prime contractor pipeline exhibits the same pattern at a larger scale:

- **PI-001/002**: 30-line file → 18 failure points → fixed by file-whole (2 failure points)
- **Prime contractor**: feature description → 12 layers → essential path is 4 layers

The difference is that the prime contractor's compensatory layers are mostly **justified** (they save real money and improve real outcomes), while PI-001/002's element decomposition for small files was **unjustified** (it created problems that didn't exist in the essential path). The prime contractor's accidental complexity is a maintenance and cognitive burden, not a functional failure — yet.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-11 | Initial analysis: 12 layers mapped (4 essential, 8 compensatory), quantified code volume, Rube Goldberg test applied, 7 recommendations |
