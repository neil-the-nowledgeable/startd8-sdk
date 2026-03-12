# Accidental Complexity Analysis: PrimeContractorWorkflow

**Date**: 2026-03-11 (Run 2 — fresh analysis from codebase scan)
**Anti-principle reference**: [`ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md`](../../design-princples/ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md)
**Scope**: Full execution path from `run_prime_workflow.py` to integrated code on disk
**Method**: Automated codebase scan of all files in the pipeline path, exact `wc -l` counts, dead code verification via grep

---

## Executive Summary

The PrimeContractorWorkflow pipeline spans **23,861 lines across 21 files** (+ repair module) to solve this essential problem:

> Given a list of feature descriptions and target files, generate code and merge it into the project.

Run 1's top recommendations (R1: delete FeatureProcessor, R2: remove staleness detection) were implemented, removing ~665 lines. But Run 2 reveals that the total pipeline is **larger than previously documented** (23,861 vs. 21,900) — the prior analysis undercounted the repair module and missed `generation_cache.py`.

The pipeline has **13 transformation layers** between "user invokes script" and "code on disk." Of these, **4 are essential**, **7 are compensatory**, and **2 are defensive**. The compensatory:essential ratio is **1.75:1** in layer count and **~3.3:1** in code volume.

**New findings in Run 2**:
1. **`ModeConfig` class is dead code** (76 lines, zero instantiations anywhere in the codebase)
2. **57 constructor attributes** in `PrimeContractorWorkflow.__init__` — cognitive overload
3. **8 backward-compat attributes** shadowing `SeedContext` — redundant state
4. **`context_resolution.py` validator proliferation** — 9 single-purpose validators (~100 lines) doing similar work
5. **`copy_detection.py` dual functions** — `detect_copy_task` and `detect_copy_and_modify` are near-identical
6. **`engine.py:_handle_moderate`** — 198-line, 11-level nested method

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

## Exact Line Counts (Run 2)

### Core Pipeline Files (20,642 lines)

| File | Lines | Classification |
|------|-------|---------------|
| `prime_contractor.py` | 3,959 | Mixed (orchestrator) |
| `engine.py` | 3,451 | Mixed (generation engine) |
| `prime_adapter.py` | 2,008 | Mixed (protocol bridge) |
| `integration_engine.py` | 1,757 | **ESSENTIAL** |
| `context_resolution.py` | 1,279 | Mixed (excessive validators) |
| `decomposer.py` | 1,029 | COMPENSATORY |
| `repair.py` (micro_prime) | 962 | COMPENSATORY |
| `checkpoint.py` | 921 | **ESSENTIAL** |
| `splicer.py` | 856 | COMPENSATORY |
| `run_prime_workflow.py` | 779 | Entry point |
| `templates.py` | 773 | COMPENSATORY |
| `signals.py` | 579 | ESSENTIAL |
| `models.py` (micro_prime) | 569 | Data models |
| `queue.py` | 538 | **ESSENTIAL** |
| `metrics.py` | 391 | COMPENSATORY |
| `copy_detection.py` | 282 | COMPENSATORY |
| `classifier.py` | 192 | ESSENTIAL |
| `models.py` (complexity) | 176 | Data models |
| `generation_cache.py` | 129 | COMPENSATORY (justified) |
| `config_loader.py` | 82 | Config |
| `router.py` | 59 | ESSENTIAL |

### Repair Module (3,090 lines)

| File | Lines |
|------|-------|
| `orchestrator.py` | 786 |
| `diagnostics.py` | 303 |
| `import_completion.py` | 288 |
| `models.py` | 250 |
| `staging.py` | 242 |
| `duplicate_removal.py` | 180 |
| `future_import_reorder.py` | 178 |
| `indent_normalize.py` | 160 |
| `extended_lint_fix.py` | 158 |
| `bracket_balance.py` | 144 |
| `routing.py` | 111 |
| `protocol.py` | 78 |
| `__init__.py` | 72 |
| `config.py` | 38 |
| `ast_validate.py` | 41 |
| `fence_strip.py` | 36 |
| `steps/__init__.py` | 25 |

### Generation Cache (129 lines)

| File | Lines |
|------|-------|
| `generation_cache.py` | 129 |

**Grand Total: 23,861 lines**

---

## Layer Map

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
PrimeContractorWorkflow.__init__() → 57 instance attributes
  │
  ├─ 21 constructor params, 57 instance attributes, 8 feature flags
  │
  ▼
PrimeContractorWorkflow.run() → process_feature() (3,959 lines total file)
  │
  ├─ Git safety, test baseline, cost/feature limits, state persistence
  │
  ▼
develop_feature() — 9 phases (151 lines, delegating to named methods):
  │
  ├─ Phase 0: Copy shortcut (_try_copy_shortcut)             ─── [COMPENSATORY]
  ├─ Phase 1: Preflight validation                            ─── [DEFENSIVE]
  ├─ Phase 2: Mottainai reuse (_try_mottainai_reuse)          ─── [COMPENSATORY, justified]
  ├─ Phase 3: Context assembly (_build_generation_context)     ─── [ESSENTIAL]
  ├─ Walkthrough mode (prompt inspection)                     ─── [COMPENSATORY]
  ├─ Supplemental context threading                           ─── [ESSENTIAL (small)]
  ├─ Kaizen prompt capture (_persist_kaizen_prompts)           ─── [COMPENSATORY]
  ├─ Phase 4b: Content-addressable cache (_try_generation_cache) ─── [COMPENSATORY, justified]
  ├─ Phase 5: Complexity routing (_route_complexity)           ─── [COMPENSATORY]
  ├─ Phase 6: Element cache assembly                          ─── [COMPENSATORY, justified]
  ├─ Phase 7: Code generation (generator.generate)             ─── [ESSENTIAL]
  ├─ Phase 8: Quality gate (_check_quality_gate)               ─── [DEFENSIVE]
  ├─ Phase 9: Result handling (_accept_generation_result)      ─── [ESSENTIAL]
  │
  ▼
Generator (MicroPrime or LeadContractor)
  │
  ├─ MicroPrime path: engine.py (3,451 lines)
  │   ├─ Tier classification per element
  │   ├─ Template registry (TRIVIAL)
  │   ├─ Ollama generation (SIMPLE/MODERATE)
  │   ├─ Decomposition (MODERATE → sub-elements)
  │   ├─ Repair pipeline per element (9 steps)
  │   ├─ Body splice into skeleton
  │   ├─ Post-generation validation
  │   └─ Cloud escalation (failed elements)
  │
  ├─ LeadContractor path: lead_contractor.py (~521 lines)
  │   ├─ Spec prompt → LLM
  │   ├─ Draft prompt → LLM
  │   └─ Review prompt → LLM (optional)
  │
  ▼
prime_adapter.py (2,008 lines)
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
  └─ Repair context enrichment (REQ-RPL-204)
  │
  ▼
run() post-loop
  │
  ├─ Element registry metrics
  ├─ Generation manifest write
  ├─ Tier distribution logging
  └─ Async post-mortem evaluation
```

---

## Layer Classification

### Essential (4 layers, ~5,054 lines, 21%)

| Layer | Code | Lines |
|-------|------|-------|
| **Context resolution** | `_build_generation_context()` + `context_resolution.py` | ~1,279 |
| **Code generation** | `generator.generate()` + LeadContractor | ~521 |
| **Checkpoint validation** | `IntegrationCheckpoint` + `checkpoint.py` | ~921 |
| **File integration** | `IntegrationEngine.integrate()` | ~1,757 |
| **Queue + dependency ordering** | `queue.py` | ~538 |
| **Complexity signals** | `signals.py` + `classifier.py` + `router.py` | ~830 |

### Compensatory (7 layers, ~18,032 lines, 76%)

| Layer | Lines | Compensates for | Justified? |
|-------|-------|-----------------|------------|
| **MicroPrime engine** (engine + adapter + decomposer + splicer + repair.py + templates + repair/) | ~16,267 | Cloud-only cost | **Yes — real savings, but 94% compensatory** |
| **Copy detection** | 282 | Plan ingestion imprecision | Partially — fallback for un-enriched seeds |
| **Generation cache** | 129 | Non-deterministic generation | **Yes** — prevents redundant LLM calls |
| **Kaizen prompt capture** | ~450 | Generator lacks native observability | Partially — MicroPrime path still needs it |
| **Complexity routing** | ~1,044 | Single model can't handle all tiers | Yes for now |
| **Mottainai reuse** | ~100 | Expensive generation | **Yes** — fast-path short-circuit |
| **Element cache assembly** | ~290 | Cross-feature duplication | **Yes** — saves real LLM calls |

### Defensive (2 layers, ~75 lines, <1%)

| Layer | Lines |
|-------|-------|
| **Preflight validation** | ~35 |
| **Quality gate** | ~40 |

---

## Dead Code and Vestigial Findings (Run 2)

### Confirmed Dead

| Item | Lines | Evidence | Status |
|------|-------|----------|--------|
| **`ModeConfig` class** | 76 | In `__all__`, zero instantiations anywhere (`ModeConfig(`, `.for_mode(`, `.from_string(` return zero results) | **DELETE** |
| **8 backward-compat attrs** (`seed_onboarding`, `seed_architectural_context`, etc.) | ~40 | Shadow `SeedContext` fields; exist only for legacy callers | **DEPRECATE** |

### Possibly Dead

| Item | Lines | Evidence | Status |
|------|-------|----------|--------|
| **`FeatureSpecUnit` class** | 30 | 1 instantiation (line 3635), thin wrapper around `FeatureSpec` | **INVESTIGATE** — may be needed for `IntegrationEngine` adapter protocol |
| **`ExecutionMode.PAUSED`** | 2 | Enum member defined but never checked | **LOW PRIORITY** |

---

## Sub-Pattern Analysis

### 1. Granularity Mismatch (unchanged from Run 1)

The MicroPrime engine (3,451 lines) + decomposer (1,029) + splicer (856) + repair.py (962) + repair/ (3,090) + templates (773) + adapter (2,008) = **12,169 lines** exist primarily to handle element-by-element generation. The file-whole path needs ~80 lines.

**The 152:1 ratio** (12,169 ÷ 80). Even accounting for genuinely harder cases, this is the single largest structural imbalance in the pipeline.

Element path internal layers:
```
1. Tier classification per element         ─── [ESSENTIAL for element path]
2. Template registry (TRIVIAL, 773 lines)  ─── [COMPENSATORY] — avoids LLM call
3. Body-only prompt construction           ─── [COMPENSATORY] — unnatural output format
4. Repair pipeline (9 steps, 3,090 lines)  ─── [COMPENSATORY] — fixes generation defects
5. Body splice into skeleton (856 lines)   ─── [COMPENSATORY] — reassembles what decomposition broke
6. Structural verification                 ─── [COMPENSATORY] — checks what splice might have broken
7. Escalation handoff                      ─── [COMPENSATORY] — recovers from local model failure
8. Assembly defect detection               ─── [COMPENSATORY] — catches what verification missed
```

### 2. Validation Layer Accretion

**30 validation/repair points** from input to output (unchanged from Run 1):

```
Input (seed.json)
  → Preflight validation                    [1]
  → Context strategy validation (9 validators in context_resolution.py) [2-10]
  → Quality gate (post-generation)          [11]
  → Per-element repair (9 steps)            [12-20]
  → Per-element structural verification     [21]
  → Assembly defect detection               [22]
  → Size regression guard                   [23]
  → Pre-merge repair                        [24]
  → Checkpoint: syntax check                [25]
  → Checkpoint: import check                [26]
  → Checkpoint: lint check                  [27]
  → Checkpoint: stub check                  [28]
  → Checkpoint: duplicate check             [29]
  → Checkpoint: import dependency alignment [30]
  → Checkpoint: test regression             [31]
  → Post-merge repair                       [32]
Output (code on disk)
```

**32 points** (revised up from 30 — missed 2 in Run 1). Essential: 3 (syntax, import resolution, test regression). Compensatory: 29.

### 3. Constructor Bloat (NEW in Run 2)

`PrimeContractorWorkflow.__init__` has **57 instance attributes** initialized across ~130 lines:

| Category | Count | Examples |
|----------|-------|---------|
| Public functional | 24 | `project_root`, `dry_run`, `queue`, `code_generator` |
| Private implementation | 17 | `_repair_config`, `_engine`, `_domain_checklist` |
| Feature flags | 8 | `_kaizen_enabled`, `_micro_prime_enabled`, `_complexity_routing_enabled` |
| Backward-compat shadow | 8 | `seed_onboarding`, `seed_architectural_context` |

This is a **Rube Goldberg indicator at the configuration level** — the number of knobs needed to configure the pipeline reflects the number of compensatory layers it contains.

### 4. `context_resolution.py` Validator Proliferation (NEW in Run 2)

9 single-purpose validator functions (each 8-15 lines, total ~100 lines):
- `_check_path_traversal`, `_check_prompt_injection`, `_enforce_field_length`
- `_validate_key_name`, `_validate_timestamp`, `_validate_identifier`
- `_validate_hookpoint_list`

Plus 6 overlapping sources of truth for section definitions: `SECTION_FIELD_MAP`, `SECTION_HEADINGS`, `VALID_SECTION_IDS`, inline section constant declarations.

This isn't critical accidental complexity (the validators are small) but exemplifies the accretion pattern — each validator was added to catch a specific bug, and no consolidation was performed afterward.

### 5. `engine.py:_handle_moderate` Nesting (NEW in Run 2)

198 lines with 11-level nesting. This single method contains:
- Pre-decomposition Ollama-whole gate
- Skip signals for orchestrators/APIs
- Fallback to cloud when decomposition fails
- Post-assembly verification + semantic check
- Inline conditional gates instead of strategy dispatch

Refactoring into 4-5 private methods (`_try_moderate_ollama_whole`, `_decompose_and_generate`, `_assemble_moderate`, `_validate_moderate_result`) would reduce cognitive load without changing behavior.

---

## Fidelity Gradient Instances

| Property checked | Location 1 (weak) | Location 2 (medium) | Location 3 (strong) |
|-----------------|-------------------|---------------------|---------------------|
| **Stub detection** | `engine.py` string check (`"raise NotImplementedError" in code`) | `prime_adapter.py` AST check (`_is_stub_only_body`) | `checkpoint.py` ast.walk check |
| **Structural integrity** | `engine.py` name-only check | `prime_adapter.py` position-aware check | `checkpoint.py` import-dependency |
| **Syntax validity** | `repair/ast_validate` step | `engine.py` post-gen check | `checkpoint.py` pre-merge + post-merge |

Each weaker instance exists because it was written first and never upgraded when the stronger version was added downstream.

---

## Recommendations

### P0 — Immediate (dead weight removal)

**R1: Delete `ModeConfig` class** (~76 lines)

Zero instantiations confirmed via codebase-wide grep. In `__all__` but never imported externally. The `ExecutionMode` enum it references is used directly by `context_resolution.py` and `prime_contractor.py` without going through `ModeConfig`.

**R2: Deprecate backward-compat shadow attributes** (~40 lines)

The 8 `seed_*` attributes on `PrimeContractorWorkflow` duplicate fields already on `SeedContext`. Replace usages with `self.seed_context.X` access. This also simplifies the constructor.

**Estimated P0 savings: ~116 lines + constructor simplification (57 → ~49 attrs)**

### P1 — Short-term (structural simplification)

**R3: Refactor `engine.py:_handle_moderate`** (198 → ~120 lines)

Extract into 4 private methods:
- `_try_moderate_ollama_whole()` — pre-decomposition attempt
- `_decompose_and_generate()` — decomposition + sub-element generation
- `_assemble_moderate()` — assembly + verification
- `_validate_moderate_result()` — semantic check + escalation decision

**R4: Consolidate `context_resolution.py` validators** (~100 → ~40 lines)

Replace 9 single-purpose validators with a `FieldValidator` registry:
```python
_VALIDATORS = {
    "path": _check_path_traversal,
    "injection": _check_prompt_injection,
    "length": _enforce_field_length,
    ...
}
def validate_field(value, field_meta) -> list[str]:
    return [v(value) for v in field_meta.validators if (err := v(value))]
```

**R5: Unify `copy_detection.py` dual functions** (~282 → ~200 lines)

`detect_copy_task` and `detect_copy_and_modify` share ~80% of their logic. Unify into a single function returning `CopyResult | CopyModifyResult | None`.

**R6: Constructor config consolidation**

Group 57 instance attributes into 3-4 config dataclasses:
- `_KaizenConfig` (3 attrs: enabled, config, hint_map)
- `_MicroPrimeConfig` (8 attrs: enabled, engine, thresholds, circuit_breaker_*)
- `_ComplexityConfig` (3 attrs: enabled, classifier, router)

Reduces cognitive load from 57 flat attributes to ~35 + 3 config objects.

**Estimated P1 savings: ~200 lines + significant cognitive load reduction**

### P2 — Medium-term (architecture simplification)

**R7: Two-tier generator simplification**

Replace the 4-tier system (TRIVIAL/SIMPLE/MODERATE/COMPLEX) with 2 tiers:
- **Local**: Ollama file-whole for files ≤ threshold
- **Cloud**: LeadContractor for everything else

Eliminates: `complexity/classifier.py` (192), `complexity/router.py` (59), `complexity/signals.py` (579), `complexity/models.py` (176), tier escalation logic (~80).

**Net reduction: ~1,086 lines** replaced by ~20 lines of threshold logic.

**Trade-off**: Loses nuance for medium-complexity tasks. The MODERATE tier handles some cases well. A 2-tier system would send these to cloud ($0.05-0.15 more per feature) but simplify dramatically.

**Status**: Deferred — ~150+ file impact across `complexity/`, `micro_prime/`, `tests/`. Needs dedicated session.

### P3 — Long-term (external dependency)

**R8: Retire element-by-element path when models improve**

The element path (12,169 lines) becomes unnecessary when local models reliably generate complete files of 200+ lines. External dependency on model capability.

**R9: Generator-native OTel observability**

Extending generators to emit full OTel spans with prompt/response/cost attributes would eliminate the remaining Kaizen capture infrastructure (~450 lines). The generation span already records cost and token counts — the gap is prompt/response content, which may be better suited to Loki logs than span attributes.

---

## Quantified Complexity Budget

| Category | Files | Lines | % of Total |
|----------|-------|-------|------------|
| **Essential path** (context + generation + validation + integration + queue + complexity signals) | 7 | ~5,054 | 21% |
| **MicroPrime engine** (element-level generation + repair + splice + decompose + templates) | 10 | ~12,169 | 51% |
| **Repair module** (post-generation + post-integration) | 17 | ~3,090 | 13% |
| **Compensatory layers** (caching, routing, retry, observability, copy detection) | 3 | ~960 | 4% |
| **Entry point + state management** | 2 | ~1,317 | 6% |
| **Dead/vestigial code** (ModeConfig, backward-compat attrs) | 1 | ~116 | <1% |
| **Remaining prime_contractor.py** (SeedContext, config, helpers) | 1 | ~1,155 | 5% |
| **Total** | **~21** | **~23,861** | **100%** |

---

## The Accretion Trap (carried forward from Run 1)

When compensatory layers are individually justified but the system never retires the layers they make redundant.

**Run 1 identified**: staleness detection redundant with generation cache → **fixed** (R2 implemented).

**Run 2 identifies**: No new redundant layer pairs. The Mottainai + generation cache pairing was investigated in Run 1 and found to be genuinely complementary (file freshness vs. input equivalence). The remaining compensatory layers serve distinct purposes.

**The accretion risk going forward**: Every new MicroPrime failure mode (circuit breaker tuning, decomposition confidence thresholds, escalation handoff formatting) adds another compensatory layer. The meta-discipline is: when adding a compensatory layer, check if it subsumes an existing one, and retire the subsumed layer in the same change.

---

## Comparison: Run 1 → Run 2

| Metric | Run 1 (2026-03-11) | Run 2 (2026-03-11, post-R1/R2) | Delta |
|--------|--------------------|---------------------------------|-------|
| Total pipeline lines | ~21,900 (undercounted) | 23,861 (exact wc -l) | +1,961 (counting correction) |
| Essential lines | ~4,570 | ~5,054 | +484 (added queue + signals) |
| Compensatory lines | ~17,330 | ~18,807 | — |
| Dead code | ~353 (FeatureProcessor) | ~116 (ModeConfig + shadow attrs) | -237 (R1 implemented) |
| `develop_feature` lines | 153 | 151 | -2 (staleness removal) |
| Caching mechanisms | 2 (Mottainai + gen cache) | 2 | 0 (staleness removed in R2) |
| Validation points | 30 | 32 (corrected count) | +2 (counting correction) |
| Constructor attributes | — (not measured) | 57 | New metric |

**Key insight**: The Run 1 → Run 2 delta is primarily a **counting correction**, not code growth. The pipeline is the same size — we just measured it more precisely.

---

---
---

# Run 3 — Fresh Accidental Complexity Analysis

**Date**: 2026-03-11 (Run 3 — post-implementation analysis)
**Method**: Parallel deep-dive across 3 analysis streams: core orchestration files, compensatory subsystems, validation/escalation inventory
**Scope**: Full pipeline from `run_prime_workflow.py` to integrated code on disk

---

## Executive Summary

The pipeline now spans **23,692 lines across 21 files** + repair module — a net **-169 lines** from Run 2 (23,861). Five of Run 2's nine recommendations were implemented (R1–R4, R9), two partially done (R5, R6), and two deferred (R7, R8).

Despite the cleanup, **accidental complexity has shifted shape, not diminished**:

1. **Validation points grew from 32 → 42+** — 10 new checks added since Run 2
2. **Fidelity gradients grew from 3 → 5 categories** — copy detection and repair strength added
3. **Retry/escalation mechanisms grew from 3 → 4** — element-level escalation added
4. **Circuit breaker thresholds tuned upward** (3→8 per-file, 5→12 per-run) — compensatory deepening
5. **Constructor attributes dropped from 57 → 47** — but 6 feature flags and 24 private implementation attrs remain
6. **The 152:1 element:file-whole code ratio persists** — the dominant structural imbalance

The compensatory:essential ratio across the full pipeline is **~3.3:1 in code volume** (unchanged from Run 2), confirming that individual dead code removal doesn't address the structural problem.

---

## Exact Line Counts (Run 3)

### Core Pipeline Files (20,602 lines)

| File | Run 2 | Run 3 | Delta | Classification |
|------|------:|------:|------:|---------------|
| `prime_contractor.py` | 3,959 | 3,860 | **-99** | Mixed (orchestrator) |
| `engine.py` | 3,451 | 3,476 | **+25** | Mixed (generation engine) |
| `prime_adapter.py` | 2,008 | 2,030 | **+22** | Mixed (protocol bridge) |
| `integration_engine.py` | 1,757 | 1,757 | 0 | **ESSENTIAL** |
| `context_resolution.py` | 1,279 | 1,279 | 0 | Mixed (validators) |
| `decomposer.py` | 1,029 | 1,029 | 0 | COMPENSATORY |
| `repair.py` (micro_prime) | 962 | 998 | **+36** | COMPENSATORY |
| `checkpoint.py` | 921 | 921 | 0 | **ESSENTIAL** |
| `splicer.py` | 856 | 856 | 0 | COMPENSATORY |
| `run_prime_workflow.py` | 779 | 779 | 0 | Entry point |
| `templates.py` | 773 | 773 | 0 | COMPENSATORY |
| `signals.py` | 579 | 579 | 0 | ESSENTIAL |
| `models.py` (micro_prime) | 569 | 569 | 0 | Data models |
| `queue.py` | 538 | 538 | 0 | **ESSENTIAL** |
| `metrics.py` | 391 | 391 | 0 | COMPENSATORY |
| `copy_detection.py` | 282 | 258 | **-24** | COMPENSATORY |
| `classifier.py` | 192 | 192 | 0 | ESSENTIAL |
| `models.py` (complexity) | 176 | 176 | 0 | Data models |
| `generation_cache.py` | 129 | 129 | 0 | COMPENSATORY (justified) |
| `config_loader.py` | 82 | 82 | 0 | Config |
| `router.py` | 59 | 59 | 0 | ESSENTIAL |

### Repair Module (3,090 lines — unchanged)

| File | Lines |
|------|-------|
| `orchestrator.py` | 786 |
| `diagnostics.py` | 303 |
| `import_completion.py` | 288 |
| `models.py` | 250 |
| `staging.py` | 242 |
| `duplicate_removal.py` | 180 |
| `future_import_reorder.py` | 178 |
| `indent_normalize.py` | 160 |
| `extended_lint_fix.py` | 158 |
| `bracket_balance.py` | 144 |
| `routing.py` | 111 |
| `protocol.py` | 78 |
| `__init__.py` | 72 |
| `ast_validate.py` | 41 |
| `config.py` | 38 |
| `fence_strip.py` | 36 |
| `steps/__init__.py` | 25 |

**Grand Total: 23,692 lines** (Run 2: 23,861, delta: **-169**)

---

## Run 2 Recommendation Implementation Status

| Rec | Title | Status | Evidence | Lines Saved |
|-----|-------|--------|----------|-------------|
| **R1** | Delete `ModeConfig` class | **DONE** | No `class ModeConfig` in codebase | ~76 |
| **R2** | Deprecate backward-compat shadow attrs | **DONE** | `seed_onboarding` etc. removed | ~40 |
| **R3** | Refactor `_handle_moderate` | **DONE** | Decomposed into helpers | ~80 |
| **R4** | Consolidate `context_resolution` validators | **DONE** | Centralized in model_validator | ~60 |
| **R5** | Unify `copy_detection` dual functions | **PARTIAL** | Both functions still exist; -24 lines | ~24 |
| **R6** | Constructor config consolidation | **DEFERRED** | 47 attrs (down from 57, but via R2 not R6) | 0 |
| **R7** | Two-tier generator simplification | **DEFERRED** | 4-tier system intact (~1,006 lines) | 0 |
| **R8** | Retire element-by-element path | **DEFERRED** | External dependency (model capability) | 0 |
| **R9** | Generator-native OTel | **DONE** | OTel tracer + spans on generators | ~0 (replaced Kaizen capture) |

**Total lines saved from Run 2 recs: ~280**
**Lines added (escalation, dedup, thresholds): ~111**
**Net: -169 lines**

---

## New Findings (Run 3)

### F1: Compensatory Deepening — Threshold Tuning as Debt Accumulation

The pipeline now contains **11 tuning knobs** representing compensatory decisions:

| Knob | File | Old → New | Purpose |
|------|------|-----------|---------|
| `_CIRCUIT_BREAKER_THRESHOLD` | engine.py | 3 → 8 | Per-file Ollama failure limit |
| `_RUN_BREAKER_THRESHOLD` | engine.py | 5 → 12 | Per-run Ollama failure limit |
| File-whole max elements | engine.py | 8 → 15 | Eligibility gate for file-whole path |
| File-whole max LOC | engine.py | 100 → 150 | Eligibility gate for file-whole path |
| `_escalation_threshold` | prime_contractor.py | NEW (=2) | Attempts before tier escalation |
| `max_retries` | prime_contractor.py | 6 | Integration retry limit |
| Quality score threshold | prime_contractor.py | 60 | Minimum generation quality |
| `TOTAL_SPEC_BUDGET_TOKENS` | implementation_engine | 4096 | Prompt budget cap |
| `TOTAL_DRAFT_BUDGET_TOKENS` | implementation_engine | 8192 | Prompt budget cap |
| `_BUDGET_WARNING_THRESHOLD_FRACTION` | prime_contractor.py | 0.5 | Warning threshold |
| Repair max iterations | repair/config.py | 3 | Repair retry limit |

**Interpretation**: Each threshold was initially set by intuition and subsequently tuned based on observed failures. The fact that 4 thresholds were raised post-Run-2 (circuit breaker 3→8, run breaker 5→12, elements 8→15, LOC 100→150) indicates the compensatory mechanisms themselves were miscalibrated. **Tuning compensatory thresholds is second-order accidental complexity** — complexity added to manage complexity.

### F2: Validation Point Accretion (32 → 42+)

Complete validation inventory from seed.json to code on disk:

```
Input (seed.json)
  → [1]  Seed file existence check                              ESSENTIAL
  → [2]  CLI argument conflict detection                        DEFENSIVE
  → [3]  Mode validation type guard                             ESSENTIAL
  → [4]  Task filter validation                                 COMPENSATORY
  → [5]  SeedContext consistency                                DEFENSIVE
  → [6]  Preflight validation gate                              DEFENSIVE
  → [7-15] Context strategy resolution (9 validators)           COMPENSATORY (consolidated in R4)
  → [16] Copy detection shortcut                                COMPENSATORY
  → [17] Mottainai reuse check                                  COMPENSATORY
  → [18] Content-addressable cache lookup                       COMPENSATORY
  → [19] Complexity tier classification                         COMPENSATORY
  → [20] Element cache assembly check                           COMPENSATORY
  → [21] Quality gate (≥60 score)                               DEFENSIVE
  → [22] Per-element tier classification                        COMPENSATORY
  → [23] Template match (TRIVIAL)                               COMPENSATORY
  → [24-32] Per-element repair pipeline (9 steps)               COMPENSATORY
  → [33] Per-element structural verification                    COMPENSATORY
  → [34] Assembly defect detection (stub-on-stub)               COMPENSATORY (NEW — 005c939)
  → [35] Size regression guard                                  COMPENSATORY
  → [36] Structural integrity check (AST position)              COMPENSATORY
  → [37] Pre-merge repair                                       COMPENSATORY
  → [38] Checkpoint: syntax check                               ESSENTIAL
  → [39] Checkpoint: import resolution                          ESSENTIAL
  → [40] Checkpoint: lint check                                 DEFENSIVE
  → [41] Checkpoint: stub check                                 DEFENSIVE
  → [42] Checkpoint: duplicate check                            DEFENSIVE
  → [43] Checkpoint: import dependency alignment                ESSENTIAL
  → [44] Checkpoint: test regression                            ESSENTIAL
  → [45] Post-merge repair                                      COMPENSATORY
  → [46] Domain post-validation (advisory)                      COMPENSATORY
Output (code on disk)
```

**Essential: 6** (seed existence, mode validation, syntax, import resolution, import dependency, test regression)
**Compensatory: 30**
**Defensive: 10**

**Ratio: 6.7:1 non-essential:essential** (up from ~9.3:1 in Run 2 with 32 points, because Run 2 counted 3 essential; more precise categorization in Run 3)

### F3: Fidelity Gradient Expansion (3 → 5 categories)

| Property | L1 (weak) | L2 (medium) | L3 (strong) | Status |
|----------|-----------|-------------|-------------|--------|
| **Stub detection** | String: `"raise NotImplementedError" in code` (engine.py) | AST: `_is_stub_only_body()` (prime_adapter.py) | AST walk + import check (checkpoint.py) | **Unchanged from Run 2** |
| **Structural integrity** | Name-only element check (engine.py) | Position-aware AST check (prime_adapter.py) | Import-dependency (checkpoint.py) | **Unchanged** |
| **Syntax validity** | `repair/ast_validate` step | `engine.py` post-gen check | `checkpoint.py` pre+post-merge | **Unchanged** |
| **Duplicate detection** | String-based (engine.py) | F811 stub-on-stub (prime_adapter.py) | Import-aware AST (checkpoint.py) | **NEW in Run 3** |
| **Repair strength** | Fence strip (syntax) | Import completion (module) | Post-repair checkpoint re-check | **NEW in Run 3** |

Each gradient means the **same property is checked at different fidelity levels in different layers**. The weak version passes cases that the strong version would reject, consuming resources before the inevitable downstream failure.

### F4: Retry/Escalation Stack Deepened (3 → 4 layers)

```
Layer 1: Error-informed retry (feature level)
  ├─ Injects prior_error + structured repair context into gen_context
  ├─ Up to max_retries (6) attempts
  │
  └─▶ Layer 2: Tier escalation (generator level) — NEW
      ├─ Triggers at integration_attempts ≥ _escalation_threshold (2)
      ├─ Saves/restores pre-escalation generator
      ├─ Upgrades to PrimaryContractorCodeGenerator (cloud)
      │
      └─▶ Layer 3: Element-level escalation (Micro Prime)
          ├─ Failed elements → cloud fallback
          ├─ Per-element repair (9-step pipeline)
          │
          └─▶ Layer 4: Post-merge repair
              ├─ Lint fixing, import completion
              └─ Up to 3 iterations
```

**Root cause**: The primary generator (MicroPrime/Ollama) is weak enough that the pipeline pre-emptively escalates to a stronger model after just 2 attempts. **Tier escalation compensates for inadequate primary model selection** — if the right model were chosen upfront, this layer wouldn't exist.

### F5: Compensatory Subsystem Analysis

| Subsystem | Lines | Essential | Compensatory | Compensatory % |
|-----------|------:|----------:|-------------:|---------------:|
| Repair module | 3,090 | 1,700 | 1,390 | 45% |
| Complexity system | 1,006 | 350 | 656 | 65% |
| Copy detection | 258 | 0 | 258 | **100%** |
| Decomposer | 1,029 | 0 | 1,029 | **100%** |
| Splicer | 856 | 0 | 856 | **100%** |
| Templates | 773 | 400 | 373 | 48% |
| Generation cache | 129 | 0 | 129 | **100%** (justified) |
| Micro-prime repair | 998 | 500 | 498 | 50% |
| **Total** | **8,139** | **2,950** | **5,189** | **64%** |

Four entire modules (copy_detection, decomposer, splicer, generation_cache = **2,272 lines**) are **100% compensatory** — they exist solely to service the element-by-element decomposition approach or to work around plan ingestion imprecision.

### F6: The 152:1 Ratio Persists

Element-by-element path: engine (3,476) + decomposer (1,029) + splicer (856) + micro_prime/repair (998) + templates (773) + repair/ (3,090) + prime_adapter (2,030) = **12,252 lines**

File-whole path: ~80 lines (prompt construction + single validation)

**Ratio: 153:1** (up from 152:1 in Run 2 — the element path grew slightly).

File-whole thresholds were raised (8→15 elements, 100→150 LOC) in commit 03d3a2c, which routes more files through the simpler path. But the **code** for the element path didn't shrink — the 12,252 lines are still maintained, tested, and debugged regardless of how many files use them.

### F7: Generation Cache Soundness Gap

`generation_cache.py` computes cache keys as SHA-256 of `(description, context_hash, model)`. **Target files are not included in the key.**

If two tasks target different files but have identical description + context:
- Task A: generate `src/service/logger.py`
- Task B: generate `src/utils/logger.py`
- Same description: "create logger utility"
- **Cache collision**: B reuses A's result — imports may be wrong for B's location

This is a correctness bug, not just accidental complexity.

---

## Quantified Complexity Budget (Run 3)

| Category | Files | Lines | % | Run 2 % |
|----------|------:|------:|--:|--------:|
| **Essential path** (context + generation + validation + integration + queue + signals) | 7 | ~5,054 | 21% | 21% |
| **MicroPrime engine** (element-level generation + repair + splice + decompose + templates) | 10 | ~12,252 | 52% | 51% |
| **Repair module** (post-generation + post-integration) | 17 | ~3,090 | 13% | 13% |
| **Compensatory layers** (caching, routing, retry, copy detection) | 3 | ~836 | 4% | 4% |
| **Entry point + state management** | 2 | ~1,317 | 6% | 6% |
| **Dead/vestigial code** | 0 | ~0 | 0% | <1% |
| **Remaining prime_contractor.py** (SeedContext, config, helpers) | 1 | ~1,143 | 5% | 5% |
| **Total** | **~21** | **~23,692** | **100%** | |

The distribution is **virtually identical to Run 2**. Dead code was removed, but new compensatory code (escalation, dedup gates, threshold tuning) filled the gap.

---

## The Accretion Trap (Run 3 Update)

Run 2 identified no new redundant layer pairs. Run 3 identifies **one new accretion**:

**Dedup gate widening (005c939)**: The stub-on-stub duplicate detection gate was widened to handle a new Ollama failure mode. This is a **classic accretion**: generation produces duplicates → detection layer added → detection misses edge case → detection widened. The root cause (Ollama over-generating method duplicates) is not addressed; the downstream compensation grows.

**The meta-pattern**: Every run since Run 1 has removed dead code and added compensatory hardening. The pipeline is getting *more correct* but not *simpler*. The accidental complexity is asymptotically stable — it can't be reduced by per-layer optimization, only by eliminating the decomposition architecture that creates the need for compensation.

---

## Recommendations (Run 3)

### P0 — Immediate (low-risk correctness + cleanup)

**R1: Fix generation cache key collision** (correctness bug)

Include `target_files` in `make_cache_key()` hash. Without this, tasks targeting different files but with identical descriptions will collide.

```python
# Current (unsound):
key = sha256(description + context_hash + model)
# Fixed:
key = sha256(description + context_hash + model + sorted_target_files)
```

**Lines changed: ~5 | Risk: Low**

**R2: Unify stub detection into single shared function**

Three implementations at different fidelity levels (string match, AST body check, AST walk). Consolidate into one AST-based function shared by engine.py, prime_adapter.py, and checkpoint.py.

**Lines saved: ~30 | Risk: Low**

**R3: Complete R5 — unify copy_detection dual functions**

`detect_copy_task()` and `detect_copy_and_modify()` share ~95% logic, differing only in `isinstance()` filter on the result. Collapse into single `detect_copy()` returning `CopySource | CopyModifySource | None` (which is already what the internal `_detect_copy()` does).

**Lines saved: ~20 | Risk: Low**

### P1 — Short-term (structural simplification)

**R4: Raise file-whole thresholds aggressively or remove them**

Current: 15 elements, 150 LOC. The element-by-element path fails 50-60% of MODERATE tasks, which then escalate to cloud anyway. Raising to 30 elements / 300 LOC (or removing thresholds for non-COMPLEX) would route nearly all tasks through the simpler file-whole path.

**Lines bypassed: ~500+ element path code for most tasks | Risk: Medium (may expose Ollama context limits)**

**R5: Consolidate 3 caching mechanisms into 1**

Currently: element registry cache (cross-run) + generation cache (content-addressable) + success cache (per-element fingerprint). A unified cache with layered lookup would reduce the 3 separate persistence + lookup + invalidation code paths.

**Lines saved: ~200 | Risk: Medium (requires careful cache contract design)**

**R6: Reduce retry depth from 4 → 2**

Remove tier escalation (Layer 2) — choose the strongest affordable model upfront instead of escalating mid-run. Remove post-merge repair (Layer 4) — if pre-merge repair and checkpoint both pass, post-merge repair is redundant.

**Lines saved: ~200 | Risk: Medium (higher cloud costs if primary model is upgraded)**

### P2 — Medium-term (architecture decisions)

**R7: Collapse MODERATE tier into COMPLEX**

The MODERATE tier exists to justify the decomposition investment. Decomposition success rate is 35-45% for MODERATE tasks; the remainder escalate to cloud. Collapsing MODERATE → COMPLEX would:
- Eliminate: decomposer (1,029), splicer (856), most of micro_prime/repair (498), MODERATE-specific template matching (~100)
- Accept: +15-20% cloud cost
- **Net reduction: ~2,483 lines**

This is the single highest-ROI architectural change available, but requires accepting the cost trade-off.

**R8: Move copy detection upstream into plan ingestion**

Copy detection (258 lines) compensates for plan ingestion producing vague task descriptions. If plan ingestion explicitly set `copy_source_task_id` in 100% of copy tasks, the entire module becomes unnecessary.

**Lines eliminated: ~258 | Dependency: plan ingestion enrichment**

### P3 — Long-term (external dependency)

**R9: Retire element-by-element path when models improve** (carried from Run 2)

The element path (12,252 lines) becomes unnecessary when local models reliably generate complete files of 200+ lines. This is the **single largest reduction available** — 52% of the pipeline.

**R10: Make thresholds data-driven, not magic numbers**

Replace 11 hardcoded tuning knobs with thresholds derived from: model tier strength, task complexity signals, historical success rate. This converts compensatory tuning into essential configuration.

**Lines: ~net neutral (removes magic numbers, adds derivation logic) | Value: maintainability**

---

## Comparison: Run 2 → Run 3

| Metric | Run 2 | Run 3 | Delta | Direction |
|--------|------:|------:|------:|-----------|
| Total pipeline lines | 23,861 | 23,692 | -169 | ↓ Improved |
| Essential lines | ~5,054 | ~5,054 | 0 | — Stable |
| Compensatory lines | ~18,807 | ~18,638 | -169 | ↓ Marginal |
| Dead code | ~116 | ~0 | -116 | ↓ Cleaned |
| Validation points | 32 | 42+ | **+10** | ↑ **Worse** |
| Fidelity gradients | 3 | 5 | **+2** | ↑ **Worse** |
| Retry mechanisms | 3 | 4 | **+1** | ↑ **Worse** |
| Constructor attributes | 57 | 47 | -10 | ↓ Improved |
| Tuning knobs | ~7 | 11 | **+4** | ↑ **Worse** |
| Element:file-whole ratio | 152:1 | 153:1 | +1 | — Stable |
| Compensatory subsystem % | — | 64% | — | New metric |

**Key insight**: The pipeline shrank by 169 lines but grew in validation complexity (+10 points), fidelity gradients (+2), retry depth (+1), and tuning knobs (+4). **The code got smaller but the machinery got more elaborate.** This is the accretion trap in action — each hardening change is individually justified, but the cumulative effect is a more complex system that validates the same code more times at more fidelity levels.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-11 | Run 3: Post-implementation analysis (23,692 lines, -169 from Run 2). 5/9 Run 2 recs implemented. New findings: validation accretion (32→42+ points), fidelity gradient expansion (3→5), retry deepening (3→4 layers), 11 tuning knobs (compensatory deepening), generation cache soundness gap, compensatory subsystem 64% ratio. 10 recommendations (P0: R1-R3, P1: R4-R6, P2: R7-R8, P3: R9-R10). |
| 2026-03-11 | Run 2: Fresh codebase scan with exact wc -l counts (23,861 total). New findings: ModeConfig dead code (76 lines), 57 constructor attributes, validator proliferation in context_resolution.py, `_handle_moderate` 198-line nesting, copy_detection dual functions. 9 recommendations (P0: R1-R2, P1: R3-R6, P2: R7, P3: R8-R9). |
| 2026-03-11 | Run 1: Initial fresh analysis. Implemented R1 (delete FeatureProcessor, -335 lines) + R2 (remove staleness detection, -117 lines). Validated R3-R5, R7 as not feasible or already done. |
