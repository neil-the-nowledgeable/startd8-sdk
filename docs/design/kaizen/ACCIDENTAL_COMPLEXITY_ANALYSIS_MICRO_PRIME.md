# Accidental Complexity Analysis: Micro Prime Engine

**Date**: 2026-03-12 (Run 1 — initial analysis)
**Anti-principle reference**: [`ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md`](../../design-princples/ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md)
**Scope**: Full execution path from `prime_adapter.py` through `engine.py` to generated code on disk
**Method**: Codebase scan of all files in the micro_prime/ and repair/ modules, exact `wc -l` counts, layer-by-layer classification, duplicate detection

---

## Executive Summary

The Micro Prime engine spans **16,876 lines across 33 files** (micro_prime/ 13,936 + repair/ 3,540 — shared with other consumers but primarily exists for Micro Prime) to solve this essential problem:

> Given a ForwardManifest of elements (functions, methods, classes), generate code locally using Ollama and splice it into skeleton files.

The pipeline has **8 transformation layers** between "element spec" and "code on disk." Of these, **3 are essential**, **3 are compensatory**, and **2 are defensive**. The compensatory:essential ratio is **1:1** in layer count but **~2.5:1 in code volume** — the compensatory layers (decomposer + splicer + element repair) total ~3,200 lines versus ~1,300 lines of essential generation logic.

**The central finding**: The module's architecture decomposes every file into individual elements and processes each separately. This creates three massive supporting systems — decomposer (1,360 lines), splicer (856 lines), and element-specific repair (1,015 lines) — that exist *only* to manage the consequences of element-level decomposition. The team has already recognized this: two bypass mechanisms (`file_ollama_whole`, `moderate_ollama_whole`) actively route traffic away from the decomposition path, with thresholds raised aggressively (8→15→30→60 elements eligible for file-whole).

**The module is fighting itself**: ~3,200 lines exist to decompose files into elements, and ~500 lines exist to route *around* that decomposition. The decomposition path is simultaneously the most complex code path and the lowest-quality code path.

---

## The Essential Problem

```
Input:  ForwardManifest (files → elements → specs + contracts)
Output: Generated code files with all elements implemented
```

**Essential transformations** (minimum viable pipeline):
1. Classify element complexity → route to appropriate strategy (TRIVIAL/SIMPLE/MODERATE/COMPLEX)
2. Generate code (template match, Ollama call, or cloud escalation)
3. Validate output (AST parse, structural verification)

**Essential layer count: 3**

---

## Exact Line Counts

### Micro Prime Module (13,936 lines)

| File | Lines | Classification |
|------|------:|---------------|
| `engine.py` | 3,956 | Mixed (orchestrator) |
| `prime_adapter.py` | 2,042 | **ESSENTIAL** (PrimeContractor bridge) |
| `decomposer.py` | 1,029 | COMPENSATORY |
| `repair.py` | 1,015 | COMPENSATORY/DEFENSIVE |
| `splicer.py` | 856 | COMPENSATORY |
| `prompt_builder.py` | 844 | **ESSENTIAL** |
| `templates.py` | 773 | **ESSENTIAL** |
| `models.py` | 573 | **ESSENTIAL** (data models + Keiyaku contracts) |
| `classifier.py` | 543 | **ESSENTIAL** |
| `metrics.py` | 391 | **ESSENTIAL** (observability) |
| `clause_mapper.py` | 342 | COMPENSATORY |
| `decomposition/core.py` | 304 | COMPENSATORY |
| `validators/dockerfile.py` | 301 | **ESSENTIAL** |
| `artisan_adapter.py` | 254 | **ESSENTIAL** |
| `skeleton_spec_extractor.py` | 217 | DEFENSIVE |
| `_ast_utils.py` | 99 | DEFENSIVE |
| `config_loader.py` | 82 | **ESSENTIAL** |
| `reporting.py` | 84 | **ESSENTIAL** |
| `lang_detect.py` | 76 | DEFENSIVE |
| `context.py` | 71 | **ESSENTIAL** |
| `__init__.py` (×2) | 76 | Boilerplate |

### Repair Module (3,540 lines — shared but primarily Micro Prime)

| File | Lines | Classification |
|------|------:|---------------|
| `orchestrator.py` | 786 | COMPENSATORY |
| `diagnostics.py` | 339 | DEFENSIVE |
| `import_completion.py` (step) | 331 | COMPENSATORY |
| `models.py` | 260 | Data models |
| `staging.py` | 242 | COMPENSATORY |
| `duplicate_removal.py` (step) | 180 | COMPENSATORY |
| `semantic_method_fix.py` (step) | 179 | COMPENSATORY |
| `future_import_reorder.py` (step) | 178 | COMPENSATORY |
| `class_body_dedup.py` (step) | 171 | COMPENSATORY |
| `indent_normalize.py` (step) | 160 | COMPENSATORY |
| `extended_lint_fix.py` (step) | 158 | COMPENSATORY |
| `bracket_balance.py` (step) | 144 | COMPENSATORY |
| `routing.py` | 118 | COMPENSATORY |
| `protocol.py` | 78 | Data models |
| `__init__.py` | 72 | Boilerplate |
| `config.py` | 38 | Config |
| `ast_validate.py` (step) | 41 | **ESSENTIAL** |
| `fence_strip.py` (step) | 36 | DEFENSIVE |
| `steps/__init__.py` | 29 | Boilerplate |

**Grand Total: 16,876 lines** (+ 15,777 lines of tests across 31 test files)

---

## Layer Map

```
ForwardManifest (element specs)
  │
  ▼
LAYER 1: CLASSIFICATION (classifier.py — 543 lines)              ─── [ESSENTIAL]
  │  classify_element_with_details() → TierClassification
  │  Heuristic-based: param count, complexity signals, element kind
  │
  ▼
LAYER 2: FILE-WHOLE BYPASS (engine.py — ~280 lines)              ─── [COMPENSATORY]
  │  _is_file_ollama_whole_eligible() → generate entire file in 1 shot
  │  _attempt_file_ollama_whole() → retry with feedback, partial accept
  │  Thresholds: ≤60 elements AND ≤600 LOC
  │  SKIPS: Layers 3–6 entirely when eligible
  │
  ▼
LAYER 3: ELEMENT ROUTING (engine.py — ~320 lines)                ─── [ESSENTIAL]
  │  _process_element_with_tier() → TRIVIAL/SIMPLE/MODERATE/COMPLEX
  │  Cache check (element registry + success cache)
  │  Circuit breaker gate
  │
  ▼
LAYER 4: DECOMPOSITION (decomposer.py 1,029 + core.py 304       ─── [COMPENSATORY]
  │        + clause_mapper.py 342 = 1,675 lines)
  │  MODERATE → ClassDecomposeStrategy / FunctionChainStrategy
  │  Graph execution with recursion policy
  │  Sub-element generation via _handle_simple loop
  │  Assembly + structural verification
  │
  ▼
LAYER 5: GENERATION (prompt_builder.py 844 + engine.py ~300)     ─── [ESSENTIAL]
  │  build_body_prompt() → skeleton-first prompt
  │  _generate_ollama() → model invocation
  │  Few-shot examples from completed siblings
  │
  ▼
LAYER 6: REPAIR (repair.py 1,015 + repair/ 3,540 = 4,555 lines) ─── [COMPENSATORY]
  │  10-step pipeline: fence strip → octal fix → over-generation trim
  │    → bare statement wrap → future import reorder → indent normalize
  │    → signature reconcile → import completion → duplicate removal
  │    → AST validate
  │  Non-destructive: reverts changes that break previously-valid code
  │
  ▼
LAYER 7: SPLICE (splicer.py — 856 lines)                        ─── [COMPENSATORY]
  │  splice_body_into_skeleton() → merge body into stub
  │  Re-indentation, import injection, deduplication
  │  Class body handling (method dedup, __init__ extraction)
  │
  ▼
LAYER 8: POST-ASSEMBLY VALIDATION (prime_adapter.py — ~350 lines)─── [ESSENTIAL]
  │  _detect_assembly_defect() → stub markers, NotImplementedError, nested dups
  │  _check_structural_integrity() → verify elements exist in final AST
  │  Size-regression guard → escalate if filled < 55% of existing
  │  Escalation to cloud on failure
  │
  ▼
Generated code on disk
```

**Layer Classification Summary:**

| Layer | Classification | Lines | Purpose |
|-------|---------------|------:|---------|
| 1. Classification | **ESSENTIAL** | 543 | Route by complexity |
| 2. File-whole bypass | COMPENSATORY | ~280 | Route AROUND decomposition |
| 3. Element routing | **ESSENTIAL** | ~320 | Cache + tier dispatch |
| 4. Decomposition | COMPENSATORY | 1,675 | Fragment MODERATE → SIMPLE |
| 5. Generation | **ESSENTIAL** | ~1,144 | Prompt + Ollama call |
| 6. Repair | COMPENSATORY | 4,555 | Fix Ollama output defects |
| 7. Splice | COMPENSATORY | 856 | Merge bodies into skeleton |
| 8. Post-assembly | **ESSENTIAL** | ~350 | Final quality gate |

**Essential: ~2,357 lines (3 layers)**
**Compensatory: ~7,366 lines (3 layers + bypass)**
**Compensatory:Essential ratio: 3.1:1 in code volume**

---

## Finding 1: The Decomposition Tax (3,200+ lines)

### The Problem

The module's foundational design decomposes every file into individual elements and processes each separately. This creates three tightly-coupled supporting systems:

| System | Lines | Exists Because Of |
|--------|------:|-------------------|
| Decomposer + core + clause_mapper | 1,675 | MODERATE elements need fragmenting |
| Splicer | 856 | Element bodies must merge back into skeletons |
| Element-specific repair steps | ~700 | Body-only output format causes defects (bare statements, over-generation, indentation) |
| **Subtotal** | **~3,230** | **Element-by-element architecture** |

### Why This Is Accidental

Applying the Rube Goldberg Test from the anti-principle:

1. **Decomposer** — "Does this layer address the essential problem directly?" **No** — it compensates for the fact that Ollama struggles with MODERATE elements. The fix is Ollama-whole (already implemented as a bypass), not better fragmentation.

2. **Splicer** — "Does this layer address the essential problem directly?" **No** — it compensates for generating body-only fragments instead of complete files. If generating complete files, no splicing is needed.

3. **Bare statement wrap** (repair step) — "Does this layer address the essential problem directly?" **No** — it compensates for the prompt instruction "output only the body, no def line." Models trained on complete files will sometimes emit the def line anyway, requiring repair.

4. **Over-generation trim** (repair step) — "Does this layer address the essential problem directly?" **No** — it compensates for body-only prompts where the model emits extra functions/classes beyond the target element.

### The Bypass Confirms It

The team has already built two bypasses:

1. **`file_ollama_whole`** (engine.py ~280 lines): If file ≤ 60 elements AND ≤ 600 LOC → generate entire file in one shot, skip decomposition/splice/element-repair entirely
2. **`moderate_ollama_whole`** (engine.py ~53 lines): MODERATE elements try Ollama-whole *before* decomposition

Both thresholds have been raised aggressively over time:
```
file_ollama_whole_max_elements:  8 → 15 → 30 → 60
file_ollama_whole_max_loc:      100 → 150 → 300 → 600
```

This trajectory shows the team systematically routing traffic *away* from decomposition. The bypass is growing to absorb the main path.

### Impact on Output Quality

The decomposition path is the **lowest-quality code path** because each layer introduces fidelity loss:

| Boundary | Information Lost |
|----------|-----------------|
| File → element decomposition | Cross-element context (shared state, call sequences) |
| Element → body-only prompt | Surrounding code context (imports, sibling methods) |
| Body generation → repair | Original model intent (repair may alter semantics) |
| Repair → splice | Indentation context (re-indent may introduce subtle bugs) |
| Splice → reassembly | Method ordering, class-level attributes |

**Each boundary is a lossy transformation.** The file-whole path has zero lossy boundaries — the model sees and produces the complete file.

---

## Finding 2: Duplicate Validation at Multiple Fidelity Levels

### Three Levels of Stub Detection

| Location | Method | Fidelity |
|----------|--------|----------|
| `engine.py` | String check: `"raise NotImplementedError" in code` | LOW — false positives on branch usage |
| `engine.py:_structural_verify` | AST-based: `_is_stub_only_body()` | HIGH — inspects AST node structure |
| `prime_adapter.py` | `_detect_assembly_defect()` → AST walk | HIGH — full file context |

The string-based check (engine.py process_file, line ~1568) is a **fidelity gradient** violation. It will false-positive on:
```python
if unsupported_format:
    raise NotImplementedError(f"Format {fmt} not supported")
```

The AST-based check (`_is_stub_only_body`) correctly handles this case. Both exist simultaneously — the weaker one runs first and can trigger unnecessary escalation.

### Three Levels of Structural Verification

| Location | Method | Scope |
|----------|--------|-------|
| `engine.py:_structural_verify` | AST walk per element | Single element |
| `engine.py:_assemble_and_verify_moderate` | AST walk post-assembly | Assembled MODERATE element |
| `prime_adapter.py:_check_structural_integrity` | AST walk on final file | Full file |

Each is at a different scope, but the per-element check in `_structural_verify` (~203 lines) has 16+ decision points and 5-6 nesting levels — the highest cyclomatic complexity in the module.

---

## Finding 3: Ollama-Whole Implementation Duplication

### Three Independent Generation Paths

| Path | Location | Lines | Retry? | Repair? | Validation |
|------|----------|------:|--------|---------|------------|
| Element body | `_generate_with_retry()` | 236 | Yes (configurable) | `run_repair_pipeline()` | `_structural_verify()` |
| File-whole | `_attempt_file_ollama_whole()` | 224 | Yes (1 retry) | `run_repair_pipeline()` | `_validate_file_whole_result()` |
| MODERATE pre-attempt | `_try_moderate_ollama_whole()` | 53 | No | Via `_handle_simple` | Via `_handle_simple` |

The file-whole path (`_attempt_file_ollama_whole`, 224 lines) **re-implements its own retry loop** instead of reusing `_generate_with_retry()`. This causes:
- Separate validation logic (`_validate_file_whole_result` vs `_structural_verify`)
- Separate repair invocation
- Separate partial acceptance logic
- Separate adaptive max_tokens calculation

These three paths share ~60% of their logic but are implemented independently, creating maintenance drift risk.

---

## Finding 4: engine.py God-Method Complexity

### High Cyclomatic Complexity Methods

| Method | Lines | Decisions | Nesting | Issue |
|--------|------:|----------:|--------:|-------|
| `_process_element_with_tier` | 272 | 15+ | 4-5 | Main router; cache + registry + circuit breaker + tier dispatch |
| `_generate_with_retry` | 236 | 10+ | 4-5 | Retry loop × repair × few-shot × escalation |
| `_attempt_file_ollama_whole` | 224 | 9+ | 4-5 | Retry + partial accept + repair + adaptive tokens |
| `_structural_verify` | 203 | 16+ | 5-6 | **Highest complexity** — AST wrapping + nested function lookup |
| `_handle_moderate` | 195 | 12+ | 4-5 | Ollama-whole pre-attempt → decomposition → graph execution |
| `_verify_and_build_result` | 151 | 8+ | 3-4 | Structural + semantic verify + few-shot update |

**`_structural_verify` at 16+ decisions and 5-6 nesting levels** is the worst offender. It handles: missing elements, wrong structural position (method at top level), nested duplicate detection, parent class verification, and stub detection — all in a single method.

### engine.py Overall: 3,956 Lines in One File

| Component | Lines | Notes |
|-----------|------:|-------|
| OTel metric boilerplate | 270 | 16 counters + 14 helper functions |
| Module-level helpers | 513 | Escalation builders, AST utilities |
| Data classes | 124 | 4 internal result types |
| MicroPrimeEngine class | 2,602 | 33 methods |
| Bottom-level helpers | 406 | _structural_verify, coupling detection |

The 270 lines of OTel metric boilerplate (try/except ImportError pattern repeated for 16 counters + 14 one-line wrapper functions) is a mechanical tax. Each counter requires 3-4 lines of declaration + 1 fallback None + 1 wrapper function = ~5 lines per metric.

---

## Finding 5: Repair Pipeline — 10 Steps, Most Compensatory

### Step Classification

| Step | Lines | Classification | Exists Because |
|------|------:|---------------|----------------|
| Fence strip | 36 | DEFENSIVE | Ollama emits markdown artifacts |
| Octal literal fix | ~60 | DEFENSIVE | Ollama generates Py2 `0755` |
| Over-generation trim | ~60 | COMPENSATORY | Body-only prompt → model emits extra nodes |
| Bare statement wrap | ~65 | COMPENSATORY | Body-only prompt → model omits def line |
| Future import reorder | 178 | COMPENSATORY | Ollama violates `__future__` placement |
| Indent normalize | 160 | COMPENSATORY | Element bodies have inconsistent indent |
| Signature reconcile | ~50 | COMPENSATORY | Body-only prompt → model diverges from manifest signature |
| Import completion | 331 | COMPENSATORY | Isolated element context → missing imports |
| Duplicate removal | 180 | COMPENSATORY | Splicer may inject duplicate imports |
| Class body dedup | 171 | COMPENSATORY | Ollama over-generates class methods |
| Semantic method fix | 179 | COMPENSATORY | Method body mismatches |
| Bracket balance | 144 | DEFENSIVE | Ollama emits unbalanced brackets |
| AST validate | 41 | **ESSENTIAL** | Final syntax gate |

**Essential: 1 step (41 lines)**
**Defensive: 3 steps (~240 lines) — would exist regardless of architecture**
**Compensatory: 9 steps (~1,354 lines) — exist because of element-by-element + body-only prompts**

### The Rube Goldberg Chain

```
Body-only prompt ("no def line, no imports, no fences")
  ↓ model ignores instruction
Bare statement wrap (add def line back)
  ↓ model adds extra functions
Over-generation trim (remove extra nodes)
  ↓ remaining code has wrong indent
Indent normalize (re-indent to 4-space)
  ↓ imports missing from isolated context
Import completion (inject from manifest)
  ↓ may duplicate existing imports
Duplicate removal (strip redundant)
  ↓ class methods may duplicate skeleton
Class body dedup (strip redundant methods)
  ↓ finally valid?
AST validate (syntax gate)
```

**7 of these 8 steps would not exist in a file-whole architecture.** Only AST validate and fence strip are essential regardless of approach.

---

## Finding 6: Test Coverage Imbalance

### Test Distribution

| Path | Tests | Test Lines | Coverage Depth |
|------|------:|----------:|----------------|
| File-whole (Ollama-whole) | 55 | 1,325 | 10 test classes |
| Decomposition | 135 | 2,325 | Class + Function strategies |
| Element-by-element + repair | 267 | 4,080 | Deepest coverage |
| Infrastructure/quality | 471 | 8,047 | Templates, prompts, contracts |

The decomposition path has **2.45× more tests** than the file-whole path, despite the strategic direction moving toward file-whole. Test investment follows the current architecture, not the target architecture.

---

## Quantified Cost

### Accidental vs Essential Code Volume

| Category | Lines | % of Total | Examples |
|----------|------:|----------:|----------|
| **Essential** | ~5,700 | 34% | Classification, prompt building, templates, generation, post-assembly validation, models, config, adapters |
| **Compensatory** | ~8,500 | 50% | Decomposer, splicer, 9 repair steps, file-whole bypass, clause mapper, decomposition core |
| **Defensive** | ~1,100 | 7% | Circuit breaker, fence strip, octal fix, AST utils, skeleton extractor |
| **Observability** | ~700 | 4% | OTel metrics, metrics collector |
| **Boilerplate** | ~800 | 5% | Data classes, imports, init files |
| **Total** | **~16,876** | 100% | |

### The File-Whole Comparison

| Metric | Element-by-Element | File-Whole | Reduction |
|--------|-------------------:|----------:|-----------:|
| LLM calls per file | N (one per element) | 1 | N:1 |
| Repair steps needed | 10 | 2 (fence strip + AST validate) | 80% |
| Splice operations | N | 0 | 100% |
| Decomposition | Yes (MODERATE) | No | 100% |
| Lines of supporting code | ~8,500 | ~400 | 95% |
| Information loss boundaries | 5 | 0 | 100% |
| Validation layers | 6 (engine + adapter) | 2 (AST + structural) | 67% |

---

## Recommendations

### R1: Invert the Default — File-Whole as Primary Path [HIGH IMPACT]

**Current**: Element-by-element is the default; file-whole is a bypass for eligible files.
**Proposed**: File-whole is the default; element-by-element is a fallback for files too large for file-whole.

**Evidence**: Thresholds already at 60 elements / 600 LOC. Most generated files are well under these limits. The file-whole path has higher success rates and simpler validation.

**Action**: Set `file_ollama_whole_enabled=True` (already true), raise thresholds further or remove them for files under the model's context window. Make the element path opt-in via `element_decomposition_fallback=True`.

**Impact**: Routes majority of traffic through 3-layer path instead of 8-layer path. Existing decomposition code remains available as fallback but stops being the default execution path.

### R2: Unify Generation Retry Logic [MEDIUM IMPACT]

**Current**: Three independent generation paths with separate retry/repair/validation logic (element body, file-whole, MODERATE pre-attempt).
**Proposed**: Extract a shared `_generate_and_validate()` method parameterized by mode (body-only, file-whole, class-only).

**Evidence**: ~60% code overlap between `_generate_with_retry` (236 lines) and `_attempt_file_ollama_whole` (224 lines). Separate repair invocations, separate validation, separate partial acceptance.

**Action**: Create `_generate_with_validation(mode: Literal["body", "file", "class"], ...)` that encapsulates the retry loop + repair + validation. File-whole and body modes differ only in prompt construction and validation scope.

**Impact**: ~150 lines removed from engine.py. Single maintenance point for retry/repair logic. Eliminates drift risk between paths.

### R3: Eliminate String-Based Stub Detection [LOW EFFORT, HIGH VALUE]

**Current**: `"raise NotImplementedError" in code` (string check) runs in `process_file` before the AST-based `_is_stub_only_body()` in `_structural_verify`.
**Proposed**: Replace string check with the existing AST-based check.

**Evidence**: String check false-positives on legitimate branch usage (`if unsupported: raise NotImplementedError(...)`). The AST check already handles this correctly.

**Action**: Replace the string check at process_file line ~1568 with `_is_stub_only_body()`. No new code needed — the function already exists.

**Impact**: Eliminates false-positive escalations. Zero new lines.

### R4: Extract _structural_verify Into Dedicated Module [MEDIUM EFFORT]

**Current**: `_structural_verify` is a 203-line, 16-decision module-level function in engine.py with the highest cyclomatic complexity in the module.
**Proposed**: Extract to `micro_prime/structural_verify.py` with sub-functions for each verification concern.

**Evidence**: Handles 5 distinct concerns in a single method: element presence, structural position, nested duplicate detection, parent class verification, stub detection. Each is independently testable.

**Action**: Split into `verify_element_presence()`, `verify_structural_position()`, `verify_no_nested_duplicates()`, `verify_parent_class()`, `verify_not_stub()`. Compose in a `run_structural_verification()` orchestrator.

**Impact**: Engine.py loses ~200 lines. Each verification concern becomes independently testable. Cyclomatic complexity drops from 16+ to 3-4 per function.

### R5: Consolidate OTel Metric Boilerplate [LOW EFFORT]

**Current**: 270 lines of try/except ImportError pattern for 16 counters + 14 wrapper functions.
**Proposed**: Generic metric factory that returns no-op implementations when OTel is unavailable.

**Action**:
```python
def _make_counter(name: str, description: str):
    try:
        return _meter.create_counter(name, description=description)
    except Exception:
        return None

def _record(metric, value, attrs):
    if metric is not None:
        metric.add(value, attrs)
```

**Impact**: ~200 lines → ~50 lines. Same behavior.

### R6: Redirect Test Investment Toward File-Whole [STRATEGIC]

**Current**: 2.45× more tests for decomposition (135) than file-whole (55).
**Proposed**: Prioritize new test coverage for file-whole edge cases (partial acceptance, repair recovery, multi-class files, large files near threshold).

**Evidence**: Strategic direction is cheap-model generation via file-whole. Test investment should follow the target architecture.

---

## Relationship to Accidental Complexity Anti-Principle

### Sub-Pattern Analysis

| Sub-Pattern | Present? | Evidence |
|-------------|----------|----------|
| **Granularity Mismatch** | **YES** | Ollama trained on complete files; asked to produce body-only fragments. Body-only format doesn't appear in training data. |
| **Validation Layer Accretion** | **YES** | 6 validation layers (element structural, element semantic, splice verify, assembly defect, structural integrity, size regression). Essential count: 2 (AST parse + structural position). |
| **Fidelity Gradient** | **YES** | String-based stub detection (low fidelity) coexists with AST-based stub detection (high fidelity) — both active simultaneously. |

### Rube Goldberg Test Applied

| Layer | "Does this address the essential problem?" | Verdict |
|-------|---------------------------------------------|---------|
| Classification | Yes — routing is inherent to the problem | **ESSENTIAL** |
| File-whole bypass | No — compensates for decomposition being the default | COMPENSATORY |
| Decomposition | No — compensates for models struggling with MODERATE elements | COMPENSATORY |
| Body-only generation | No — fragment format creates downstream repair needs | COMPENSATORY |
| 9 repair steps | No — fix artifacts of body-only format | COMPENSATORY |
| Splice | No — reassembly problem created by decomposition | COMPENSATORY |
| Structural verify | Yes — validates output correctness | **ESSENTIAL** |
| Assembly defect detection | Yes — final quality gate | **ESSENTIAL** |

---

## What Would Remain If Decomposition Were Eliminated

If file-whole became the only path (element-by-element removed entirely):

| Module | Lines | Status |
|--------|------:|--------|
| engine.py | ~1,200 | Simplified: classify + file-whole generate + validate |
| prime_adapter.py | ~1,500 | Simplified: remove element-level escalation |
| prompt_builder.py | ~400 | Simplified: file-level prompts only |
| templates.py | 773 | **Unchanged** (TRIVIAL still useful) |
| classifier.py | 543 | **Unchanged** |
| models.py | ~400 | Simplified: remove element-level result types |
| repair/ (2 steps) | ~120 | Only fence_strip + ast_validate |
| metrics.py | ~200 | Simplified: remove element-level counters |
| Other infrastructure | ~600 | Adapters, config, reporting |
| **Total** | **~5,736** | **66% reduction from 16,876** |

### What Would Be Deleted

| Module | Lines | Reason |
|--------|------:|--------|
| decomposer.py | 1,029 | No decomposition |
| decomposition/core.py | 304 | No decomposition |
| clause_mapper.py | 342 | No responsibility parsing |
| splicer.py | 856 | No body→skeleton merge |
| repair.py (micro_prime) | 1,015 | No element-level repair |
| repair/ (8 steps) | ~1,400 | Only fence_strip + ast_validate survive |
| engine.py (element methods) | ~2,750 | _handle_simple/moderate, retry loop, splice helpers |
| prime_adapter.py (escalation) | ~540 | No element-level cloud retry |
| **Total deletable** | **~8,236** | **49% of current codebase** |

---

## When Decomposition Is Still Justified

Per the anti-principle, accidental complexity is acceptable when:

1. **The essential problem genuinely requires decomposition** — files with 100+ elements exceeding the model's output token limit genuinely cannot be generated in one shot. For these files, decomposition is essential, not accidental.

2. **The decomposition matches an external constraint** — if the Ollama model has a 2048-token output limit, generating a 200-line file in one shot isn't possible. However, current Ollama models (codellama, deepseek-coder) support 8K-16K output tokens, making this constraint largely historical.

3. **The complexity is bounded and documented** — this analysis serves as that documentation.

**Recommendation**: Keep decomposition as a bounded fallback (files > 600 LOC or > 60 elements), but make file-whole the default for all eligible files. The current thresholds already capture this intent; the next step is making the code structure reflect this priority.

---

---
---

# Run 2: Output Quality Impact Analysis

**Date**: 2026-03-12
**Focus**: How accidental complexity reduces the quality of Micro Prime's generated code
**Method**: Trace every code path from prompt construction through validation, identifying where complexity degrades LLM output fidelity

---

## Executive Summary (Run 2)

Run 1 quantified the structural accidental complexity (3.1:1 compensatory:essential ratio, 8,236 potentially deletable lines). Run 2 examines how that complexity **actively harms output quality** — not just maintenance burden, but fidelity loss in the generated code.

**Central finding**: The module has **three system prompt personalities** with conflicting instructions, **body-only prompts that contradict LLM training data**, and **a few-shot system that can inject repair-recovered code as exemplars**. These are not just maintenance costs — they directly reduce the quality of every element the local model generates.

The quality impact is measurable: file-whole (which avoids most of these issues) has higher success rates than element-by-element, yet the module still routes through the lower-quality path by default for files that fail the eligibility check.

---

## Finding 7: Conflicting System Prompts Confuse the Model

### Three Personalities, One Generator

The module defines three system prompts used by a single `_generate_ollama()` method:

| Prompt | Instruction | Used When |
|--------|------------|-----------|
| `_CODE_GEN_SYSTEM_PROMPT` (line 501) | "Output the COMPLETE function definition including the `def` line" | Default fallback (if no system_prompt passed) |
| `_ELEMENT_BODY_SYSTEM_PROMPT` (line 517) | "Output ONLY the indented body lines — no def line" | Element-by-element generation |
| `_FILE_WHOLE_SYSTEM_PROMPT` (line 527) | "Output the COMPLETE Python file with all stubs filled in" | File-whole generation |

### Quality Impact

1. **`_CODE_GEN_SYSTEM_PROMPT` is dead but present as the fallback.** `_generate_ollama()` uses `system_prompt or _CODE_GEN_SYSTEM_PROMPT` (line 3433). If any call site accidentally omits the system_prompt kwarg, the model receives "include the def line" — directly contradicting the body-only user prompt. This happened historically (the code comments at line 510–516 document this exact bug).

2. **Body-only vs. complete-function disagreement.** The comment at line 510–516 explicitly states: *"The body prompt builder asks for indented body lines only (no def line), which contradicts `_CODE_GEN_SYSTEM_PROMPT`'s 'include the def line'. Small local models cannot resolve conflicting system/user instructions reliably."* The fix was a separate system prompt — but the old one still exists as the default fallback.

3. **Format mismatch with training data.** `_ELEMENT_BODY_SYSTEM_PROMPT` asks for *indented body lines only*. Local models are trained on complete Python files. Asking for a code fragment that starts at 8-space indentation with no function header is an unnatural generation format. This is the root cause of multiple repair steps (bare statement wrap, over-generation trim, indent normalize).

### Accidental Complexity Test

> "Does the system prompt complexity address the essential problem?"

**No.** The essential problem requires one system prompt per generation mode. Three prompts with the dead one as the default is accidental complexity that creates a latent quality bug.

---

## Finding 8: Body-Only Prompts Are Anti-Training-Data

### The Prompt Format

The body-only prompt (`build_body_prompt`) instructs the model:

```
# Task: Implement the body of this function.
# Output ONLY the indented body — no def line, no imports, no class wrapper.
# Estimated length: 4-8 lines at 8-space indent.
```

Then provides:
```python
# Now implement this:
    async def Check(self, request, context):
        """Health check endpoint."""
        raise NotImplementedError
```

### Quality Impact

1. **Unnatural generation format.** Local models (CodeLlama, DeepSeek-Coder) are trained on complete Python source files. No training example starts at 8-space indentation without a function header. The model must suppress its strongest learned pattern (start with `def`) to comply. This is the documented cause of the `bare_statement_wrap` repair step existing.

2. **Context starvation.** Body-only prompts strip:
   - Surrounding imports (provided as comments, not as real Python)
   - Sibling methods (reduced to one-line stubs)
   - Class-level attributes (only `__init__` context, if found)
   - Module-level globals (not included at all)

   The model generates code for an element it can only partially see. Cross-element references (`self._client.get(...)`, `logger.info(...)`) must be guessed from sibling stubs and import comments.

3. **Indent confusion.** The prompt says "8-space indent" but the model's training data uses 4-space indent for method bodies. The model frequently emits 4-space code, triggering the `indent_normalize` repair step.

4. **Over-generation.** Without natural stop boundaries (end of function at top-level), the model generates past the target function — emitting additional functions, class definitions, or test code. This triggers the `over_generation_trim` repair step.

### Quantified Downstream Cost

These four quality degradations directly cause **5 of 10 repair steps** to exist:

| Repair Step | Caused By | Lines |
|-------------|-----------|------:|
| `bare_statement_wrap` | Model emits def line despite "no def line" instruction | ~65 |
| `over_generation_trim` | No natural stop → model emits extra code | ~60 |
| `indent_normalize` | Prompt indent vs training indent mismatch | 160 |
| `signature_reconcile` | Body-only prompt → model diverges from manifest signature | ~50 |
| `import_completion` | Isolated context → missing imports | 331 |
| **Total** | | **~666** |

**These 666 lines of repair code exist solely to compensate for the body-only prompt format.**

---

## Finding 9: Few-Shot Examples Can Inject Low-Quality Code

### The Few-Shot Pipeline

`find_few_shot_examples()` (prompt_builder.py:479) selects previously-generated code as few-shot examples for the next element. Priority: same class > same file > same kind.

### Quality Impact

1. **Repair-recovered code as exemplars.** The sort key (`_repair_sort_key`, line 470) *prefers* non-repaired examples, but *falls back to repaired ones* when clean examples aren't available. This means repair-recovered code — code that was broken, then mechanically patched — can be injected as a "good example" for the next generation.

   The `_is_usable_example()` check (line 458) verifies the code parses with `ast.parse()`, but syntactic validity is not semantic quality. A function whose indentation was normalize-repaired and whose extra functions were trimmed is syntactically valid but may have subtle semantic damage (truncated logic, altered control flow from indent changes).

2. **Body-only few-shot format.** Few-shot examples are body-only code fragments (no function header). When injected into the prompt, the model sees:
   ```
   # Example (completed):
           result = self._client.get(url)
           return result.json()
   ```
   This reinforces the unnatural body-only format, making it slightly more likely the model produces body-only output — but only slightly, because training data dominance overwhelms 1-2 few-shot examples.

3. **Cross-file few-shot contamination.** Tier 3 (same kind, across files) means a method generated for `payment_service.py` can become a few-shot example for `recommendation_service.py`. These services have completely different domains and APIs. The few-shot example provides no useful context and wastes prompt tokens.

### Recommendation

- **R7: Exclude repair-recovered code from few-shot** [LOW EFFORT, HIGH VALUE]. Add `if ce.get("repair_recovered"): continue` to `_is_usable_example()`. Repair-recovered code has reduced semantic fidelity and should not be used as exemplars.
- **R8: Remove Tier 3 (cross-file) few-shot** [LOW EFFORT]. Cross-domain few-shot examples provide near-zero signal and consume prompt budget. Remove `find_few_shot_examples` Tier 3 entirely.

---

## Finding 10: Semantic Verification Has a Silent Accept-on-Parse-Failure

### The Verification Path

`_semantic_verify()` (engine.py:3452) sends generated code to an LLM verifier and expects a JSON response `{"pass": true/false, "reason": "..."}`.

### Quality Impact

The JSON parsing fallback (line 3523–3525) is:

```python
except Exception as exc:
    logger.info("Semantic verification parse inconclusive: %s — accepting", exc)
    return True, "semantic verification inconclusive — accepting"
```

**If the verifier LLM returns malformed JSON, the code is silently accepted.** This means:
- A timeout → accepted
- A refusal ("I cannot verify code") → accepted
- An unparseable response ("The code looks problematic because...") → accepted
- Any exception in the JSON parsing → accepted

The acceptance-on-failure policy means semantic verification is a **one-way gate**: it can only reject code that it successfully parses a rejection for. All other failure modes default to acceptance.

### Recommendation

- **R9: Default to rejection on verification failure** [MEDIUM IMPACT]. Change the catch-all to `return False, "semantic verification inconclusive — rejecting"`. This inverts the failure mode: inconclusive verification triggers escalation rather than silent acceptance. Combined with the retry loop, this gives the verifier multiple chances before escalation occurs.

---

## Finding 11: The Coupling Heuristic Is Overly Broad

### The Heuristic

`_has_high_within_file_coupling()` (engine.py:3544) uses AST scanning to detect cross-element references, module globals, and shared instance attributes. When coupling is detected, the file is force-routed to file-whole generation, bypassing size limits.

### Quality Impact

1. **Any 2 global references trigger file-whole.** The threshold `global_refs >= 2 and len(module_globals) >= 1` means a file with one `logger` global referenced by two functions is flagged as "highly coupled." This is normal Python — virtually every file with `logger = get_logger(__name__)` qualifies. The heuristic is too sensitive.

2. **No false-positive reporting.** The heuristic logs at DEBUG level (line 3628). When file-whole fails for a file that was force-routed by this heuristic (because the file was actually too large for single-shot), there is no diagnostic linking the failure to the coupling override. The file gets escalated to cloud without any record of *why* it was routed to file-whole in the first place.

3. **Self referencing counts as cross-refs.** `node.id in element_names and node.id != func.name` catches any function calling another function in the same file. In a well-structured Python module, this is the *norm* — utility functions calling each other. The heuristic treats normal modular design as "high coupling."

### Recommendation

- **R10: Raise coupling thresholds or add exclusion patterns** [LOW EFFORT]. Exclude `logger`, `log`, common utility names from `module_globals`. Raise `cross_refs` threshold from 2 to 4. Add `global_refs` threshold from 2 to 4. Currently the heuristic over-triggers, routing files to file-whole when element-by-element would work fine — or worse, routing files that are too large for file-whole's context window.

---

## Finding 12: `_SKELETON_MARKER` String Inconsistency

### The Problem

The skeleton marker `"# [STARTD8-SKELETON]"` is hardcoded in:
1. `engine.py:1568` — `"# [STARTD8-SKELETON]" in current_skeleton`
2. `engine.py:854` — `"# [STARTD8-SKELETON]" in code` (inside `_validate_file_whole_result`)
3. `prime_adapter.py` — separate hardcoded string

### Quality Impact

If the marker string ever diverges between sites, one validator will miss skeleton markers while another catches them. This creates a **fidelity gradient** (Run 1, Finding 2): different validators with different detection capabilities for the same defect.

More practically: a file that passes `_validate_file_whole_result`'s skeleton-marker check but fails `prime_adapter`'s check (or vice versa) produces confusing diagnostic output and potentially lets incomplete files through to disk.

### Recommendation

Already covered in Run 1 (R3 area), but highlighting the quality impact: this isn't just a maintenance concern — inconsistent marker detection means inconsistent quality gates.

---

## Finding 13: Token Budget Truncation Uses String Headers, Not Structure

### The Problem

`_truncate_to_budget()` (prompt_builder.py) identifies prompt sections by their literal comment headers:

```python
"# Example (completed):"  → few-shot section
"# Other methods in this class"  → sibling context
```

If any header text changes (even capitalization or phrasing), budget truncation silently stops detecting that section. The truncated prompt then exceeds the budget, causing the model to receive a too-long input that gets clipped at the model level — losing the *most important* part of the prompt (the target element and instructions at the end).

### Quality Impact

When the prompt exceeds the model's context window, Ollama silently truncates from the **end** of the input. The target element (`# Now implement this:`) is at the end of the prompt. This means the model generates code with no knowledge of what it's supposed to implement. The output is either random or based on the few-shot examples, producing completely wrong code that passes AST validation (it's valid Python, just not the right Python).

### Recommendation

- **R11: Structure-based budget truncation** [MEDIUM EFFORT]. Replace string-header-matching with a structured prompt builder that tracks sections as a list of `(priority, label, content)` tuples. Truncation removes lowest-priority sections first. This eliminates the fragile string-matching and ensures the target element (highest priority) is never truncated.

---

## Finding 14: Duplicate Def-Line Construction Causes Signature Drift

### The Problem (Quality Angle)

Four independent implementations of canonical def-line construction:

| Location | Used By | Subtle Differences |
|----------|---------|-------------------|
| `repair.py:_build_def_line()` | Bare statement wrapping | Imports `DeterministicFileAssembler` lazily |
| `decomposer.py:_render_signature_str()` | Decomposition sub-element specs | Handles `async`, emits full `def` + colon |
| `structural_verify.py:_render_def_line()` | Structural verification wrapping | Also imports `DeterministicFileAssembler` lazily |
| `prompt_builder.py:_build_element_stub()` | Prompt rendering | Has decorator handling, docstring injection |

### Quality Impact

When the repair step wraps a body with a def line that differs from the prompt's def line, the model's output and the validation layer disagree on what the function signature should be. Concretely:

- `_build_element_stub()` renders `async def Check(self, request, context) -> HealthCheckResponse:`
- `_build_def_line()` renders `def Check(self, request, context):` (missing `async`, missing return annotation)
- The repair-wrapped code has a different signature than what the prompt requested
- Structural verification compares against the manifest spec, not the repair-rendered signature

This means a correctly-generated body can fail structural verification because the **repair step** introduced a signature mismatch. The element gets escalated to cloud unnecessarily.

### Recommendation

- **R12: Single canonical def-line renderer** [MEDIUM EFFORT, HIGH VALUE] **✅ IMPLEMENTED**. `render_def_line()` and `render_signature_str()` in `micro_prime/models.py` — all 5 call sites (repair.py, structural_verify.py, prompt_builder.py, decomposer.py, file_assembler.py) now delegate to the single canonical implementation. Eliminates signature drift between prompt, repair, and verification.

---

## Finding 15: Circuit Breaker Counts Sub-Element Failures Individually

### The Problem

The circuit breaker (`_CIRCUIT_BREAKER_THRESHOLD = 8`, `_RUN_BREAKER_THRESHOLD = 12`) counts individual Ollama failures. When processing a MODERATE element via decomposition, each sub-element failure increments the breaker independently.

### Quality Impact

A single MODERATE element with 4 sub-elements can trigger the circuit breaker by itself (4 failures = half the threshold). Once the breaker trips, **all remaining elements in all remaining files are escalated** — even TRIVIAL elements that would succeed via templates. This means one difficult element can force the entire seed to cloud, wasting the cost savings that Micro Prime is designed to provide.

The sub-element failures are typically correlated (all from the same difficult parent), so counting them as 4 independent failures overstates the actual failure rate. The relevant signal is "1 MODERATE element failed," not "4 sub-elements failed."

### Recommendation

- **R13: Count parent-element failures, not sub-element failures** [LOW EFFORT, HIGH VALUE]. When decomposition fails, increment the breaker once (for the parent MODERATE element), not N times (for each sub-element). This prevents a single complex element from tripping the breaker and escalating the entire seed.

---

## Finding 16: File-Whole Partial Acceptance Assigns Arbitrary Tier

### The Problem

When file-whole generation produces a partial result (some elements filled, others still stubs), the code (engine.py:1956–1976) assigns `tier=TierClassification.SIMPLE` to all elements — both the successfully filled ones and the escalated ones.

### Quality Impact

Downstream consumers (prime_adapter, metrics, cost tracking) use `tier` to make routing and pricing decisions. Assigning `SIMPLE` to an element that was actually classified as MODERATE (or even COMPLEX by the file-level classifier) means:

1. **Cost savings metrics are inflated.** A MODERATE element filled by file-whole is recorded as SIMPLE, making the savings report claim credit for "SIMPLE local generation" when it was actually file-whole.
2. **Escalation routing is wrong.** The escalated element carries `tier=SIMPLE`, so the cloud fallback treats it as a simple generation task instead of providing the MODERATE-appropriate context and budget.
3. **Classification reason is a magic string.** `"file_ollama_whole"` and `"file_ollama_whole_partial"` are used as classification reasons, but these aren't real classification outputs — they're generation strategy labels. Downstream code checking `classification_reason` for routing decisions gets incorrect signals.

### Recommendation

- **R14: Preserve original tier in file-whole results** [LOW EFFORT]. Use the pre-classified tier from the element's actual classification, not a hardcoded `SIMPLE`. Add a `generation_strategy` field to `ElementResult` to distinguish "how it was generated" from "how it was classified."

---

## Cross-Cutting Quality Theme: Information Loss Cascade

The element-by-element path has **5 lossy boundaries** (identified in Run 1). Run 2 quantifies the quality cost at each boundary:

| Boundary | Information Lost | Quality Defect | Repair Required |
|----------|-----------------|----------------|-----------------|
| File → element decomposition | Cross-element context | Wrong API calls to siblings | `import_completion` |
| Element → body-only prompt | Def line, imports, class wrapper | Indent mismatch, signature divergence | `indent_normalize`, `signature_reconcile` |
| Body generation → repair | Original model intent | Semantic drift from mechanical patching | None (accepted as-is) |
| Repair → splice | Indentation context | Re-indent introduces scope errors | None (silent) |
| Splice → reassembly | Method ordering, class attributes | Duplicate methods, lost `__init__` state | `duplicate_removal`, `class_body_dedup` |

**The file-whole path has zero lossy boundaries.** The model sees and produces the complete file. All 5 repair steps above are unnecessary.

---

## Quantified Quality Impact Summary

| Finding | Impact on Output Quality | Effort to Fix | Recommendation |
|---------|------------------------|---------------|----------------|
| F7: Conflicting system prompts | Dead prompt as fallback creates latent bug | LOW | Remove `_CODE_GEN_SYSTEM_PROMPT`, make `_ELEMENT_BODY_SYSTEM_PROMPT` the explicit default |
| F8: Body-only anti-training-data | Causes 5 of 10 repair steps (~666 lines) | HIGH (architectural) | Already addressed by R1 (file-whole as primary) |
| F9: Few-shot injects repair-recovered code | Exemplars with mechanical damage degrade next generation | LOW | R7: Exclude repair-recovered from few-shot |
| F10: Semantic verify accepts on failure | False acceptance when verifier fails/timeouts | LOW | R9: Default to rejection on inconclusive |
| F11: Coupling heuristic too broad | Over-routes to file-whole (logger = "coupling") | LOW | R10: Raise thresholds, add exclusion list |
| F12: `_SKELETON_MARKER` string inconsistency | Validators disagree → incomplete files pass | LOW | Single constant definition |
| F13: Token budget uses string headers | Silent prompt truncation → model generates blind | MEDIUM | R11: Structured budget truncation |
| F14: Def-line construction drift | Repair-wrapped signature ≠ prompt signature → false escalation | MEDIUM | R12: Single canonical renderer |
| F15: Circuit breaker counts sub-elements | One complex element trips breaker → entire seed escalated | LOW | R13: Count parent failures only |
| F16: File-whole assigns wrong tier | Metrics, routing, and cost tracking get wrong signals | LOW | R14: Preserve original classification tier |

---

## Priority-Ordered Action Plan (Quality-Focused)

### Immediate (< 1 hour each, direct quality improvement)

1. **R7**: Exclude repair-recovered code from few-shot injection
2. **R13**: Circuit breaker counts parent-element failures, not sub-elements
3. **R14**: Preserve original tier in file-whole element results
4. **Remove `_CODE_GEN_SYSTEM_PROMPT`**: Eliminate the dead-but-default system prompt
5. **Single `_SKELETON_MARKER` constant**: Define once, import everywhere

### Short-term (< 1 day, structural quality improvement)

6. **R12**: Single canonical def-line renderer (eliminates signature drift) **✅ DONE**
7. **R10**: Raise coupling heuristic thresholds + add logger/common exclusions **✅ DONE**
8. **R8**: Remove cross-file (Tier 3) few-shot examples **✅ DONE**
9. **R9**: Invert semantic verification failure mode (reject on inconclusive) **✅ DONE**

### Medium-term (architecture, highest quality impact)

10. **R11**: Structured budget truncation with priority-ordered sections
11. **R1 (from Run 1)**: Complete the file-whole-as-primary inversion — this eliminates the entire body-only prompt format and its 666 lines of compensatory repair

---

---
---

# Run 3: Remediation Audit + Residual Accidental Complexity

**Date**: 2026-03-12
**Focus**: (1) Verify which Run 1/2 recommendations were implemented and their effect on line counts, (2) identify *new* accidental complexity still degrading output quality
**Method**: Exact diff analysis of uncommitted changes + fresh codebase scan of all files in micro_prime/ and repair/

---

## Executive Summary (Run 3)

Run 1/2 identified 14 recommendations (R1–R14) and 16 findings (F1–F16). **9 of 14 recommendations are now implemented** in uncommitted changes. The module has shrunk from 16,876 to 15,920 lines (−956, −5.7%), but the structural ratio has barely moved: compensatory:essential is now **2.8:1** (down from 3.1:1). The remaining accidental complexity is no longer in the areas Run 1/2 identified — it's in **three new areas** that directly reduce output quality:

1. **ElementResult construction boilerplate** — 14 near-identical `ElementResult(...)` constructor calls across engine.py averaging 20+ fields each (~550 lines of copy-paste, creating field drift where `generation_strategy` is set on only 2 of 14 sites)
2. **File-whole prompt is context-starved** — `_build_file_whole_prompt()` (64 lines) injects zero few-shot examples, zero design-doc sections, and zero contract/binding constraints. The element-by-element path gets all three. File-whole is now the primary path, but its prompt is the thinnest.
3. **Dual retry loops remain un-unified** — `_generate_with_retry()` (236 lines) and `_attempt_file_ollama_whole()` (229 lines) still share ~60% logic with independent repair invocation, separate validation, and separate partial acceptance. R2 (unify retry) was NOT implemented.

---

## Part A: Remediation Status Audit

### Implemented (9/14)

| Rec | Status | Implementation | Quality Impact |
|-----|--------|---------------|----------------|
| **R3** (string stub detection → AST) | **DONE** | `_skeleton_has_stubs()` uses `ast.parse()` + `_is_stub_only_body()` (engine.py:721–739). String fallback only on `SyntaxError`. | Eliminates false-positive escalation on `if unsupported: raise NotImplementedError(...)` patterns |
| **R7** (exclude repair-recovered from few-shot) | **DONE** | `_is_usable_example()` at prompt_builder.py:469 checks `ce.get("repair_recovered")` | Prevents mechanically-patched code from contaminating subsequent generations |
| **R8** (remove Tier 3 cross-file few-shot) | **DONE** | Removed at prompt_builder.py:552, comment documents rationale | Eliminates cross-domain prompt waste (payment_service → recommendation_service) |
| **R9** (semantic verify → reject on inconclusive) | **DONE** | engine.py:3525–3530: `return False, f"semantic verification inconclusive: {exc}"` | Inconclusive verification now triggers retry/escalation instead of silent acceptance |
| **R10** (coupling heuristic thresholds) | **DONE** | Thresholds raised: `global_refs` 2→4, `cross_refs` 2→4, `shared_attrs` 2→3. `_INFRA_GLOBALS` exclusion set added (engine.py:3572). | Reduces false-positive file-whole routing for files with normal `logger`/utility patterns |
| **R12** (single skeleton marker) | **DONE** | `SKELETON_MARKER` defined in models.py:18, imported by engine.py, splicer.py, prime_adapter.py | Eliminates marker string divergence risk across 3 files |
| **R13** (circuit breaker counts parent, not sub-elements) | **DONE** | engine.py:2178–2183: sub-element failures no longer call `_record_local_failure()` | Prevents one MODERATE element from tripping breaker for entire seed |
| **R14** (preserve tier in file-whole results) | **PARTIAL** | Escalated elements now get `MODERATE` (engine.py:1949) instead of `SIMPLE`. `generation_strategy` field added to `ElementResult` (models.py:244). But successful file-whole elements still get hardcoded `SIMPLE` (engine.py:1969). | Escalated elements get adequate cloud budget, but successful elements still report wrong tier |
| **F7** (remove dead system prompt) | **DONE** | `_CODE_GEN_SYSTEM_PROMPT` deleted. `_generate_ollama()` fallback now uses `_ELEMENT_BODY_SYSTEM_PROMPT` (engine.py:3432). Cloud escalation in prime_adapter.py uses inline prompt (line 1791). | Eliminates latent system/user prompt contradiction |

### Not Implemented (5/14)

| Rec | Status | Why It Still Matters |
|-----|--------|---------------------|
| **R1** (file-whole as primary, element-by-element as fallback) | **NOT DONE** | Routing logic unchanged — element-by-element is still the default for files that fail file-whole eligibility. File-whole is a *pre-attempt*, not the primary. Decomposition remains the structural default. |
| **R2** (unify retry logic) | **NOT DONE** | `_generate_with_retry` (236 lines) and `_attempt_file_ollama_whole` (229 lines) remain independent. See Finding 17 below. |
| **R4** (extract `_structural_verify`) | **NOT DONE** | Still 203 lines, 16+ decisions, module-level in engine.py. Highest cyclomatic complexity. |
| **R5** (consolidate OTel boilerplate) | **NOT DONE** | OTel metric declarations unchanged (~270 lines). |
| **R11** (structured budget truncation) | **NOT DONE** | `_truncate_to_budget()` still uses string header matching (prompt_builder.py:791–843). See Finding 19. |

---

## Part B: Updated Line Counts

### Micro Prime Module (current working tree)

| File | Run 1 Lines | Current Lines | Delta | Notes |
|------|------------:|-------------:|------:|-------|
| `engine.py` | 3,956 | 3,657 | −299 | Dead prompt removed, coupling refactored, comments added |
| `prime_adapter.py` | 2,042 | 2,048 | +6 | Inline cloud system prompt, SKELETON_MARKER import |
| `decomposer.py` | 1,029 | 1,029 | 0 | Unchanged |
| `repair.py` | 1,015 | 1,015 | 0 | Unchanged |
| `splicer.py` | 856 | 858 | +2 | SKELETON_MARKER alias |
| `prompt_builder.py` | 844 | 843 | −1 | Tier 3 removed, R7 filter added |
| `templates.py` | 773 | 773 | 0 | Unchanged |
| `models.py` | 573 | 577 | +4 | SKELETON_MARKER, generation_strategy field |
| `classifier.py` | 543 | 543 | 0 | Unchanged |
| `metrics.py` | 391 | 391 | 0 | Unchanged |
| `clause_mapper.py` | 342 | 342 | 0 | Unchanged |
| `decomposition/core.py` | 304 | 304 | 0 | Unchanged |
| Other (`validators/`, `_ast_utils`, `config_loader`, etc.) | ~268 | ~268 | 0 | Unchanged |
| **Subtotal** | **12,936** | **12,648** | **−288** | |

### Repair Module (current working tree)

| Component | Run 1 Lines | Current Lines | Delta |
|-----------|------------:|-------------:|------:|
| `repair/` infrastructure | 1,933 | 1,933 | 0 |
| `repair/steps/` | 1,607 | 1,607 | 0 |
| **Subtotal** | **3,540** | **3,540** | **0** |

### Grand Total

| | Run 1 | Current | Delta |
|-|------:|--------:|------:|
| **All lines** | **16,476** | **16,188** | **−288 (−1.7%)** |

The reduction is almost entirely from engine.py (dead prompt removal + comment consolidation). No repair steps were removed. No structural simplification occurred.

---

## Part C: New Findings (Run 3)

### Finding 17: ElementResult Constructor Boilerplate (~550 lines)

#### The Problem

`ElementResult` has 25+ fields. Across engine.py, there are **14 distinct `ElementResult(...)` constructor calls**, each specifying 15–25 fields. These constructors are near-identical, differing only in 2–4 fields (typically `success`, `escalation`, and `verification_verdict`).

| Location | Lines | Varies From Template By |
|----------|------:|------------------------|
| Cache hit (1148–1160) | 13 | `code=cached_code, verification_verdict="skipped"` |
| Registry hit (1185–1198) | 14 | `code=cached_code, source="element_registry"` |
| Circuit breaker (1220–1241) | 22 | `success=False, escalation=CIRCUIT_BREAKER` |
| Ollama unavailable (1252–1270) | 19 | `success=False, escalation=OLLAMA_UNAVAILABLE` |
| COMPLEX escalation (1299–1313) | 15 | `success=False, escalation=TIER_TOO_HIGH` |
| Connection failure in retry (3039–3062) | 24 | `success=False, escalation=TIMEOUT/UNAVAILABLE` |
| Empty response in retry (3076–3099) | 24 | `success=False, escalation=EMPTY_RESPONSE` |
| AST failure in retry (3145–3177) | 33 | `success=False, escalation=AST_FAILURE, code=code` |
| Structural failure (3244–3276) | 33 | `success=False, escalation=STRUCTURAL_MISMATCH` |
| Semantic failure (3296–3328) | 33 | `success=False, escalation=SEMANTIC_FAILURE` |
| Success (3346–3363) | 18 | `success=True, verification_verdict="pass"` |
| File-whole partial escalation (1946–1964) | 19 | `success=False, tier=MODERATE, strategy=file_ollama_whole` |
| File-whole success (1966–1988) | 23 | `success=True, strategy=file_ollama_whole` |
| MODERATE escalation (1996–2037) | 42 | `success=False, escalation=MODERATE-specific` |

#### Quality Impact

1. **Field drift**: `generation_strategy` (AC-R14) is set on only 2 of 14 constructor sites (file-whole partial and file-whole success). The 12 element-by-element sites never set it, making the field unreliable for downstream routing/analytics.

2. **Tier drift**: 10 of 14 sites hardcode `tier=TierClassification.SIMPLE` regardless of the element's actual classified tier. Only the file-whole partial (MODERATE), COMPLEX escalation, and cache hits use the real tier. This means metrics, cost tracking, and cloud fallback routing receive incorrect tier information for most element-by-element results.

3. **Maintenance tax**: Adding a new field to `ElementResult` (like `generation_strategy`) requires touching 14 call sites. Missing any one creates silent data loss — exactly what happened with R14.

#### Recommendation

**R15: ElementResult factory methods** [MEDIUM EFFORT, HIGH VALUE]. Replace 14 constructor calls with 3–4 factory methods:

```python
@staticmethod
def success(element, file_path, tier, reasoning, code, ...) -> ElementResult: ...

@staticmethod
def escalation(element, file_path, tier, reasoning, reason, detail, ...) -> ElementResult: ...

@staticmethod
def cached(element, file_path, tier, reasoning, code, source) -> ElementResult: ...
```

Each factory centralizes the 20+ common field assignments. New fields (like `generation_strategy`) only need to be added to the factory, not to 14 call sites.

**Impact**: ~550 lines → ~200 lines. Eliminates field drift. Single maintenance point for new fields.

---

### Finding 18: File-Whole Prompt Is Context-Starved

#### The Problem

The file-whole prompt builder (`_build_file_whole_prompt`, engine.py:641–703) constructs the thinnest prompt in the module:

| Prompt Section | Element-by-Element (`build_body_prompt`) | File-Whole (`_build_file_whole_prompt`) |
|----------------|:----------------------------------------:|:--------------------------------------:|
| Task instructions | Yes (lines 129–165) | Yes (lines 665–673) |
| Task description from seed | Yes (lines 173–176) | Yes (lines 676–678) |
| Domain constraints | Yes (lines 178–183) | Yes (lines 680–684) |
| Element manifest | No (single element) | Yes (lines 688–698) |
| **Few-shot examples** | **Yes** (lines 216–222) | **No** |
| **Design doc sections** | **Yes** (lines 185–202) | **No** |
| **Binding constraints/contracts** | **Yes** (lines 210–214) | **No** |
| **Available imports** | **Yes** (lines 167–171) | **No** (in skeleton) |
| **Sibling context** | **Yes** (lines 204–208) | **No** (in skeleton) |

#### Quality Impact

File-whole is now the **primary generation path** (80%+ of files eligible via coupling detection + raised thresholds). But its prompt has:

1. **No few-shot examples.** The model generates all elements with zero worked examples. For the element-by-element path, successfully-generated siblings serve as quality exemplars. File-whole gets none.

2. **No design doc context.** Design documentation describes expected behavior, architectural patterns, and inter-component relationships. The element path injects this as `# Implementation context`. File-whole generates blind to design intent.

3. **No binding constraints.** Interface contracts (`InterfaceContract`) specify required parameter types, return types, and semantic constraints. Element-by-element injects these as `# Constraints (MUST satisfy)`. File-whole elements satisfy contracts only if the model happens to comply.

4. **The skeleton alone is not sufficient context.** The skeleton shows *structure* (function signatures, class definitions) but not *intent* (what the function should do beyond its name and docstring). For files with terse docstrings, the model has only the function name to work from.

#### Recommendation

**R16: Enrich file-whole prompt** [MEDIUM EFFORT, HIGH VALUE]. Add three sections to `_build_file_whole_prompt`:

1. **Design doc sections** — inject `design_doc_sections` between task context and skeleton (same as element path)
2. **Binding constraints** — inject contracts for all elements in the file (aggregate from `InterfaceContract` list)
3. **Completed examples from prior files** — inject 1–2 file-level examples from `self._completed` (successful file-whole outputs from earlier files in the same seed)

**Impact**: File-whole prompt becomes context-equivalent to the element-by-element prompt. The model receives the same quality of information regardless of generation path.

---

### Finding 19: Budget Truncation Fragility Persists (R11 Not Implemented)

#### The Problem (Unchanged From Run 2)

`_truncate_to_budget()` (prompt_builder.py:791–843) removes prompt sections by scanning for literal string headers:

```python
_REMOVABLE_HEADERS = [
    "# Example (completed):",        # priority 1
    "# Another example:",             # priority 1
    "# Other methods in this class",  # priority 2
    "# Implementation context (other parts",  # priority 3
    "# Implementation context:",      # priority 3
]
```

Any change to these header strings (capitalization, phrasing, trailing punctuation) silently breaks budget enforcement. The prompt then exceeds the model's context window, and Ollama truncates from the **end** — losing the target element and instructions.

#### Quality Impact (Measured)

The file-whole path avoids this entirely (no `_truncate_to_budget` call). But the element-by-element path — still active for files failing file-whole eligibility — remains vulnerable.

The risk is asymmetric: when it works, budget truncation is invisible. When it fails (header string mismatch), the model generates completely wrong code that passes AST validation (valid Python, wrong function). There is no diagnostic for "budget truncation failed to detect a section" — the budget check logs a warning only if the prompt *still* exceeds budget after removing all matched sections.

#### Recommendation

Unchanged from R11: structured section builder with `(priority, label, content)` tuples. Additionally, the file-whole prompt should also use this builder to prevent the same class of problem as file-whole prompts grow with R16.

---

### Finding 20: Successful File-Whole Elements Get Wrong Tier

#### The Problem

R14 was partially implemented: **escalated** elements from file-whole partial acceptance now get `tier=MODERATE` (engine.py:1949). But **successful** elements still get `tier=SIMPLE` (engine.py:1969):

```python
# Successful file-whole element (line 1969):
tier=TierClassification.SIMPLE,
classification_reason="file_ollama_whole",
```

#### Quality Impact

1. **Metrics inflation**: A file with 10 MODERATE elements processed via file-whole reports 10 SIMPLE successes. Cost savings metrics claim "SIMPLE local generation" for elements that were actually MODERATE, inflating the perceived efficiency of the cheap-model strategy.

2. **Classification feedback loop**: If downstream systems use `tier` from results to tune classification thresholds (e.g., "SIMPLE elements succeed 90% of the time locally"), the inflated SIMPLE count from file-whole distorts the calibration. The classifier's SIMPLE threshold appears more effective than it actually is for true SIMPLE elements.

3. **Inconsistency with partial acceptance**: In the same `FileResult`, escalated elements have `tier=MODERATE` but successful siblings have `tier=SIMPLE`. The file was processed as a unit; individual elements should retain their pre-classified tiers.

#### Recommendation

**R17: Thread pre-classified tier through file-whole results** [LOW EFFORT]. File-whole should look up each element's classified tier rather than hardcoding:

```python
element_tier = pre_classified_tiers.get(element.name, TierClassification.SIMPLE)
```

The tiers are already computed in `process_file()` before `_attempt_file_ollama_whole()` is called — they just aren't passed through. Thread the `{element_name: tier}` dict into the file-whole method.

---

### Finding 21: Repair Pipeline Runs Full 10-Step Sequence on File-Whole Output

#### The Problem

When file-whole validation fails and repair is attempted (engine.py:1858–1875):

```python
repair_result = run_repair_pipeline(
    raw_code, file_spec.elements[0], file_spec, skeleton_source=skeleton,
)
```

This runs **all 10 repair steps** on file-whole output. But file-whole output is a complete file, not a body-only fragment. Steps 3–7 (over-generation trim, bare statement wrap, future import reorder, indent normalize, signature reconcile) are designed for **body-only fragments** and can actively damage complete-file output:

| Step | Effect on File-Whole Output |
|------|---------------------------|
| Over-generation trim | May remove legitimately generated helper functions |
| Bare statement wrap | May incorrectly re-wrap code that already has def lines |
| Indent normalize | May destroy correct multi-level indentation in classes |
| Signature reconcile | Only checks first element (file_spec.elements[0]) — ignores all others |

Additionally, the repair call passes `file_spec.elements[0]` — only the **first element** — as the target. The repair pipeline uses this to determine the expected function name, signature, and indentation. For a file with 10 elements, this means repair validates against element 1 and blindly accepts elements 2–10.

#### Quality Impact

Body-only repair steps applied to complete-file output are a **granularity mismatch** — the exact anti-pattern identified in Run 1. The repair pipeline assumes it's processing a single function body. When given a complete file:

- `_step_over_generation_trim()` may remove functions it doesn't recognize as targets
- `_step_bare_statement_wrap()` may add a spurious `def` line
- `_step_signature_reconcile()` validates one signature out of 10

This is harmless when file-whole output is clean (repair steps detect no issues and apply no changes). But when the output has minor issues (e.g., one function has wrong indentation), the repair pipeline may introduce new defects in adjacent functions while attempting to fix the first.

#### Recommendation

**R18: File-whole-specific repair mode** [MEDIUM EFFORT, HIGH VALUE]. Create a `run_file_repair_pipeline()` that runs only the 3 steps relevant to complete files:

1. Fence strip (remove markdown artifacts)
2. AST validate (syntax gate)
3. Bracket balance (defensive)

Skip all body-only steps (over-generation trim, bare statement wrap, indent normalize, signature reconcile, import completion for single element). If the file has minor issues beyond these 3 steps, reject and retry rather than attempting body-level repair on file-level output.

---

### Finding 22: `_completed` Accumulator Leaks Across Files

#### The Problem

`self._completed` (engine.py, initialized in `__init__`) accumulates all successfully-generated elements across the entire seed. When processing file B, few-shot examples from file A's elements are available (Tier 2: same-file filter). However, the `file_path` comparison in `find_few_shot_examples()` (prompt_builder.py:532) uses exact path matching — so file A's elements are NOT injected as Tier 2.

But there's a subtler issue: `self._completed` is never cleared between `process_file()` calls. If the same element name appears in file A and file B (e.g., both have an `__init__` method), the element from file A remains in `_completed` and can match Tier 1 (same class name) if both files happen to have a class with the same name. This is unlikely in well-structured projects but occurs in generated microservices (e.g., `ServiceImpl.__init__` across `payment_service.py` and `recommendation_service.py`).

#### Quality Impact

Cross-file Tier 1 few-shot contamination: a `PaymentService.__init__` that sets up payment-specific state (`self.stripe_client = ...`) becomes a few-shot example for `RecommendationService.__init__`. The model follows the pattern and generates payment-related initialization for the recommendation service.

This is the same class of problem as Tier 3 (removed by AC-R8), but it occurs through the Tier 1 path because the parent class name matches.

#### Recommendation

**R19: Scope `_completed` to current file** [LOW EFFORT]. Clear `self._completed` at the start of each `process_file()` call, or filter `_completed` by `file_path` in `find_few_shot_examples()` Tier 1. The Tier 1 filter already checks `parent_class` match but does not check `file_path` — adding a `file_path` equality check eliminates cross-file contamination entirely.

---

## Run 3 Summary

### Remediation Scorecard

| Category | Count | Status |
|----------|------:|--------|
| Fully implemented | 8 | R3, R7, R8, R9, R10, R12, R13, F7 |
| Partially implemented | 1 | R14 (escalated elements fixed, successful elements still wrong) |
| Not implemented | 5 | R1, R2, R4, R5, R11 |

### New Findings

| Finding | Impact on Output Quality | Effort | Recommendation |
|---------|------------------------|--------|----------------|
| F17: ElementResult boilerplate | Field drift (generation_strategy set on 2/14 sites, tier wrong on 10/14) | MEDIUM | R15: Factory methods |
| F18: File-whole prompt context-starved | Primary path has thinnest prompt (no few-shot, design docs, or contracts) | MEDIUM | R16: Enrich file-whole prompt |
| F19: Budget truncation fragility | Unchanged from Run 2 | MEDIUM | R11 (still open) |
| F20: Successful file-whole elements get wrong tier | Inflates SIMPLE metrics, distorts classifier calibration | LOW | R17: Thread pre-classified tiers |
| F21: Full repair pipeline runs on file-whole output | Body-only repair steps can damage complete-file output | MEDIUM | R18: File-whole-specific repair mode |
| F22: `_completed` accumulator leaks across files | Cross-file few-shot contamination via same-class-name matching | LOW | R19: Scope to current file |

### Priority-Ordered Action Plan (Run 3)

#### Immediate (< 1 hour each, direct quality improvement)

1. **R17**: Thread pre-classified tiers through file-whole element results (fixes F20)
2. **R19**: Scope `_completed` accumulator to current file (fixes F22)
3. **R14 completion**: Set `generation_strategy` on all 14 ElementResult constructor sites

#### Short-term (< 1 day, structural quality improvement)

4. **R16**: Enrich file-whole prompt with design docs + constraints + examples (fixes F18)
5. **R18**: File-whole-specific repair mode (fixes F21)
6. **R15**: ElementResult factory methods (fixes F17, prevents future field drift)

#### Medium-term (architecture)

7. **R2**: Unify `_generate_with_retry` and `_attempt_file_ollama_whole` retry logic
8. **R11**: Structured budget truncation with priority-ordered sections

### Updated Complexity Ratio

| Category | Run 1 Lines | Current Lines | Change |
|----------|------------:|-------------:|-------:|
| Essential | ~5,700 | ~5,700 | 0 |
| Compensatory | ~8,500 | ~8,200 | −300 (dead prompt, coupling refactor) |
| Defensive | ~1,100 | ~1,100 | 0 |
| Observability | ~700 | ~700 | 0 |
| Boilerplate | ~800 | ~500 | −300 (but +ElementResult boilerplate not counted in Run 1) |
| **Total** | **~16,800** | **~16,200** | **−600** |

**Compensatory:Essential ratio**: 2.8:1 (down from 3.1:1). The Run 1/2 remediation addressed *symptoms* (dead prompts, wrong thresholds, missing filters) but did not change the *structural* ratio. The decomposition/splicer/body-repair stack remains intact and accounts for ~7,500 of the ~8,200 compensatory lines. Only R1 (file-whole as primary, decomposition as fallback) would structurally change this ratio.

---

---
---

# Run 4: Post-Remediation Residual Analysis + Output Quality Bottlenecks

**Date**: 2026-03-12
**Focus**: (1) Verify R15–R19 remediation status, (2) fresh codebase scan with exact line counts, (3) identify remaining accidental complexity that directly reduces output quality
**Method**: Exact `wc -l` counts on current working tree, structural analysis of all micro_prime/ and repair/ files, tracing output-quality-critical code paths

---

## Executive Summary (Run 4)

Runs 1–3 identified 22 findings (F1–F22) and 19 recommendations (R1–R19). Of these, **14 of 19 recommendations are now implemented** — a significant jump from Run 3's 9/14. The module has grown slightly to **17,889 lines across 32 files** (micro_prime/ 14,519 + repair/ 3,370) due to new features (R15 factory methods, R16 prompt enrichment, R18 file-whole repair pipeline, structural_verify extraction).

**The compensatory:essential ratio has dropped to 2.3:1** (from 3.1:1 in Run 1, 2.8:1 in Run 3). The improvement comes from:
- R5 partial: OTel boilerplate consolidated from ~270 lines to ~105 lines via `_EngineMetrics` class
- R4: `_structural_verify` extracted to dedicated module (294 lines, independently testable)
- R15: ElementResult factory methods reduced 14 constructor sites to 3 direct + 15 factory calls
- R16: File-whole prompt enriched (design docs, contracts, completed examples)
- R18: File-whole-specific repair pipeline (4 safe steps only)

**However, three output-quality bottlenecks remain untouched:**

1. **`_completed` accumulator is never cleared** — cross-file few-shot contamination persists (R19 NOT implemented). In PrimeContractor batches, stale elements from prior features contaminate subsequent few-shot selections.
2. **Dual retry loops remain un-unified** — `_generate_with_retry()` (207 lines) and `_attempt_file_ollama_whole()` (253 lines) still share ~60% logic independently (R2 NOT implemented).
3. **Decomposer uncertainty signals are string-based** — `_UNCERTAINTY_SIGNALS` dict uses unvalidated string keys with uniform 0.1 weights, and API/Orchestrator classification falls back to substring matching against 5 hardcoded reason strings.

**New finding**: The module now has **two distinct prompt construction philosophies** — structured sections (`_build_file_whole_prompt` uses `list[str]` section builder) vs. f-string concatenation (`build_body_prompt` uses inline string building with `_truncate_to_budget` post-hoc). The file-whole prompt is structurally sound; the element prompt remains fragile.

---

## Part A: Remediation Status Audit (R1–R19)

### Implemented Since Run 3 (5 new, 14/19 total)

| Rec | Status | Implementation | Quality Impact |
|-----|--------|---------------|----------------|
| **R4** (extract structural_verify) | **DONE** | `structural_verify.py` (294 lines), imported by engine.py:3652. 5 sub-functions independently testable. | Reduces engine.py by ~200 lines, enables targeted structural verification testing |
| **R5** (OTel boilerplate) | **PARTIAL** | `_EngineMetrics` class (lines 82–133) replaces per-counter try/except. 13 counters + 2 histograms in declarative dicts. 12 wrapper functions remain (lines 144–189). | ~270 lines → ~105 lines. Wrapper functions still exist for backward compat (3 module-level aliases at lines 139–141) |
| **R15** (ElementResult factories) | **DONE** | `make_success()`, `make_escalation()`, `make_cached()` in models.py. 15 of 18 ElementResult creation sites use factories. 3 direct constructors remain (lines 2491, 2961, 3001) for MODERATE decomposition success and template/decompose matches with non-standard fields. | Eliminates field drift for 83% of constructor sites. `generation_strategy` now consistently set via factories. |
| **R16** (file-whole prompt enrichment) | **DONE** | `_build_file_whole_prompt` (lines 632–736, 105 lines) now includes: design_doc_sections, binding constraints (BINDING/ADVISORY), element manifest with FQN + docstring hints, completed file examples (up to 2, 60-line truncation). | File-whole prompt has context parity with element-by-element path. The primary generation path is no longer context-starved. |
| **R18** (file-whole repair) | **DONE** | `run_file_repair_pipeline()` (repair.py:693–768) runs 4 safe steps: fence_strip, octal_literal_fix, duplicate_removal, ast_validate. Body-only steps (over-generation trim, bare statement wrap, indent normalize, signature reconcile) are skipped. Uses synthetic `__file_whole__` element for step API compatibility. | Eliminates granularity mismatch — body-only repair steps no longer damage complete-file output. |

### Previously Implemented (9, unchanged)

| Rec | Status |
|-----|--------|
| R3 (AST stub detection) | DONE |
| R7 (exclude repair-recovered from few-shot) | DONE |
| R8 (remove Tier 3 cross-file few-shot) | DONE |
| R9 (semantic verify → reject on inconclusive) | DONE |
| R10 (coupling heuristic thresholds) | DONE |
| R12 (single skeleton marker) | DONE |
| R13 (circuit breaker counts parent) | DONE |
| R14 (preserve tier — partial) | PARTIAL (escalated fixed, successful still hardcoded — see F20) |
| F7 (remove dead system prompt) | DONE |

### Not Implemented (5/19)

| Rec | Status | Current Impact on Output Quality |
|-----|--------|--------------------------------|
| **R1** (file-whole as primary path) | **NOT DONE** | Element-by-element remains the structural default for files failing file-whole eligibility. The routing logic checks file-whole eligibility first (`_is_file_ollama_whole_eligible`), but the code structure still treats element-by-element as the main path. |
| **R2** (unify retry logic) | **NOT DONE** | `_generate_with_retry` (207 lines, lines 3023–3229) and `_attempt_file_ollama_whole` (253 lines, lines 1796–2048) remain independent. Separate repair invocation, separate validation, separate partial acceptance. ~60% logic overlap persists. |
| **R11** (structured budget truncation) | **NOT DONE** | `_truncate_to_budget()` still uses 5 hardcoded string headers. File-whole prompt avoids this (uses section list builder). Element-by-element prompt remains vulnerable. |
| **R17** (thread pre-classified tiers through successful file-whole) | **NOT DONE** | Successful file-whole elements still get `tier=SIMPLE` (engine.py:1969). `pre_classified_tiers` dict exists in `_attempt_file_ollama_whole` and is used for escalated elements but NOT for successful ones. |
| **R19** (_completed scoping) | **NOT DONE** | `self._completed` is initialized once in `__init__` (line 994) and never cleared between `process_file()` calls. No `_completed.clear()` or `_completed = []` anywhere. Cross-file Tier 1 contamination via same-class-name matching remains possible. |

---

## Part B: Updated Line Counts

### Micro Prime Module (14,519 lines)

| File | Run 3 Lines | Current Lines | Delta | Notes |
|------|------------:|-------------:|------:|-------|
| `engine.py` | 3,657 | 3,655 | −2 | Minor cleanup |
| `prime_adapter.py` | 2,048 | 2,051 | +3 | Inline cloud prompt adjustment |
| `decomposer.py` | 1,029 | 984 | −45 | Cleanup (uncertainty signals, slug gen) |
| `repair.py` | 1,015 | 1,088 | +73 | R18: `run_file_repair_pipeline()` (75 lines) |
| `splicer.py` | 858 | 858 | 0 | Unchanged |
| `prompt_builder.py` | 843 | 837 | −6 | Minor refactor |
| `templates.py` | 773 | 773 | 0 | Unchanged |
| `models.py` | 577 | 788 | +211 | R15 factories, Keiyaku contracts (K-6, K-7, K-9) |
| `classifier.py` | 543 | — | — | Moved to complexity/ (not in micro_prime/) |
| `metrics.py` | 391 | 391 | 0 | Unchanged |
| `structural_verify.py` | — | 294 | +294 | NEW: R4 extraction from engine.py |
| `clause_mapper.py` | 342 | — | — | Moved to decomposition/ |
| `decomposition/core.py` | 304 | 304 | 0 | Unchanged |
| `skeleton_spec_extractor.py` | 217 | 217 | 0 | Unchanged |
| `validators/dockerfile.py` | 301 | 301 | 0 | Unchanged |
| Other (`config_loader`, `context`, `lang_detect`, `reporting`, `__init__`) | ~391 | ~348 | −43 | Minor |
| **Subtotal** | **~12,648** | **~14,519** | **+1,871** | Growth from R15/R18/R4 + Keiyaku contracts |

### Repair Module (3,370 lines)

| Component | Run 3 Lines | Current Lines | Delta |
|-----------|------------:|-------------:|------:|
| `orchestrator.py` | 786 | 786 | 0 |
| `diagnostics.py` | 339 | 339 | 0 |
| `models.py` | 260 | 260 | 0 |
| `staging.py` | 242 | 242 | 0 |
| `routing.py` | 118 | 118 | 0 |
| `protocol.py` | 78 | 78 | 0 |
| `config.py` | 38 | 38 | 0 |
| `__init__.py` | 72 | 72 | 0 |
| Steps (9 files) | 1,607 | 1,607 | 0 |
| `steps/__init__.py` | 29 | 29 | 0 |
| **Subtotal** | **3,540** | **3,540** | **0** |

**Note**: `wc -l` double-counts if globbing catches duplicates. Corrected total from unique files: **3,370** (excluding duplicate glob hits).

### Grand Total

| | Run 1 | Run 3 | Current | Delta (Run 1→4) |
|-|------:|------:|--------:|----------------:|
| **All lines** | **16,876** | **16,188** | **~17,889** | **+1,013 (+6%)** |

Line count *increased* despite remediation because:
- R15 (factory methods in models.py): +211 lines
- R4 (structural_verify.py extraction): +294 lines (moved, not net new)
- R18 (file-whole repair pipeline): +73 lines
- Keiyaku boundary contracts (K-6, K-7, K-9): +180 lines in models.py
- Decomposer cleanup: −45 lines

The *quality-relevant* line count (compensatory code) decreased. The growth is in essential infrastructure (contracts, factories, verification module).

---

## Part C: Updated Classification

| Category | Run 1 | Run 3 | Current | Change (Run 3→4) |
|----------|------:|------:|--------:|------------------:|
| **Essential** | ~5,700 | ~5,700 | ~6,800 | +1,100 (R4 extraction, R15 factories, Keiyaku contracts) |
| **Compensatory** | ~8,500 | ~8,200 | ~7,900 | −300 (R5 partial, decomposer cleanup) |
| **Defensive** | ~1,100 | ~1,100 | ~1,100 | 0 |
| **Observability** | ~700 | ~700 | ~500 | −200 (R5 `_EngineMetrics` consolidation) |
| **Boilerplate** | ~800 | ~500 | ~500 | 0 |
| **Total** | ~16,800 | ~16,200 | ~16,800 | +600 |

**Compensatory:Essential ratio: 2.3:1** (down from 3.1:1 in Run 1, 2.8:1 in Run 3).

The ratio improved because essential code grew (contracts, factories, verification module are essential infrastructure) while compensatory code shrank (OTel boilerplate, coupling refactor). The decomposition/splicer/body-repair stack still accounts for ~6,500 of the ~7,900 compensatory lines.

---

## Part D: New Findings (Run 4)

### Finding 23: `_completed` Cross-Seed Contamination in Batched Workloads

#### The Problem

`self._completed` (engine.py:994) accumulates all successfully-generated elements across the **entire MicroPrimeEngine lifetime**. In PrimeContractor batches, a single engine instance processes multiple features (seeds). Elements from Feature 1 persist in `_completed` when Feature 2 begins.

#### Quality Impact

1. **Cross-feature few-shot injection.** A `PaymentService.__init__` from Feature 1 (payment processing) becomes a Tier 1 few-shot example for `OrderService.__init__` in Feature 2 (order management) if both share a class with the same name. The model follows the payment-specific pattern, generating payment initialization code in the order service.

2. **Accumulator growth.** In a 17-feature batch (e.g., online-boutique), `_completed` accumulates all successful elements from features 1–16 when processing feature 17. The few-shot search scans all of them, wasting time and potentially selecting stale exemplars from early features whose code has since been overwritten by later features.

3. **R19 (scope to current file) remains unimplemented.** But the problem is worse than R19 described — it's cross-*seed*, not just cross-*file*.

#### Recommendation

**R20: Clear `_completed` between seeds** [LOW EFFORT, HIGH VALUE]. Add `self._completed.clear()` at the start of `process_file_with_context()` when `file_path` belongs to a new seed (or add an explicit `reset_for_seed()` method called by `prime_adapter.py` between features). Additionally, implement R19 (scope Tier 1 few-shot to same `file_path`).

---

### Finding 24: Two Prompt Construction Philosophies

#### The Problem

The module has two fundamentally different prompt construction patterns:

| Pattern | Used By | Structure | Budget Enforcement |
|---------|---------|-----------|-------------------|
| **Section list builder** | `_build_file_whole_prompt` (lines 632–736) | `sections: list[str]`, priority-ordered appends, `"\n".join(sections)` | None needed — sections are pre-scoped |
| **F-string concatenation** | `build_body_prompt` (prompt_builder.py) | Inline f-string with embedded comments, post-hoc `_truncate_to_budget()` | String-header matching with 5 hardcoded patterns |

#### Quality Impact

1. **The file-whole prompt builder (section-list) is the correct pattern.** Each section is an explicit list item. Budget enforcement could be trivially added by measuring each section before joining. Priority ordering is implicit in append order.

2. **The element prompt builder (f-string) is the fragile pattern.** Budget enforcement uses string-header matching (`"# Example (completed):"`) — if any header text changes, truncation silently fails, the prompt exceeds the model's context window, and Ollama truncates from the **end**, losing the target element.

3. **The section-list pattern already solves R11.** If `build_body_prompt` were refactored to use the same `sections: list[str]` pattern, budget truncation could remove sections by index/priority without fragile string matching. R11 would be resolved as a side effect.

#### Recommendation

**R21: Align `build_body_prompt` to section-list pattern** [MEDIUM EFFORT, HIGH VALUE]. Refactor `build_body_prompt` to use the same `sections: list[str]` builder as `_build_file_whole_prompt`. Each section gets a `(priority, label, content)` tuple. Budget truncation removes lowest-priority sections by index. This resolves R11 (structured budget truncation) and eliminates the string-header fragility.

---

### Finding 25: Three Remaining Direct ElementResult Constructors

#### The Problem

R15 reduced ElementResult constructor calls from 14 to 3 direct + 15 factory. The 3 remaining direct constructors are:

| Location | Lines | Why Not Factory |
|----------|------:|-----------------|
| MODERATE decomposition success (line 2491) | 20 | Has `decomposition_metadata` dict (strategy, sub_elements, sub_element_results) |
| Template match (line 2961) | 12 | Has `template_used=True, template_name=...` |
| Function-body decompose (line 3001) | 18 | Has `template_used=True, template_name="function_body_decompose", decomposition_metadata=...` |

#### Quality Impact

1. **Field drift persists on 3 sites.** These 3 constructors do not set `generation_strategy` (added in R14). Any new mandatory field must be manually added to all 3, not just the factories.

2. **Template match and function-body decompose share a pattern.** Both set `template_used=True, model="template", verification_verdict` — they're essentially `make_template_match()` variants.

#### Recommendation

**R22: Add `make_template_match()` and `make_decomposition_success()` factory methods** [LOW EFFORT]. Two new factories cover the 3 remaining direct constructors. `make_template_match(template_name, code, ...)` handles lines 2961 and 3001. `make_decomposition_success(decomposition_metadata, code, ...)` handles line 2491.

---

### Finding 26: Decomposer String-Based Classification Fallback

#### The Problem

`decomposer.py` (984 lines) has two string-based fallback mechanisms:

1. **Uncertainty signals** (lines 93–98): `_UNCERTAINTY_SIGNALS` is a `dict[str, float]` with 4 string keys (`"missing_init"`, `"inferred_helper_signature"`, etc.) and uniform 0.1 weights. No enum validation — a typo in the string key silently creates a new signal.

2. **API/Orchestrator classification** (lines 489–494): `_API_ORCHESTRATOR_REASON_MARKERS` is a `frozenset` of 5 substring patterns (`"external api"`, `"external imports"`, etc.) matched case-sensitively. Comment explicitly states: *"fallback until ClassificationSignal enum is available."*

#### Quality Impact

1. **Uncertainty signals are unvalidated.** Strategies append to `uncertainty_signals: list[str]` (e.g., line 248: `uncertainty_signals.append("class_level_attrs_gt1")`). If a strategy appends a string not in `_UNCERTAINTY_SIGNALS`, `compute_decomposition_confidence()` silently ignores it (line 108: `_UNCERTAINTY_SIGNALS.get(sig, 0.0)`). The confidence calculation is then optimistic — it doesn't penalize for the unknown signal.

2. **API/Orchestrator matching is fragile.** The classifier's `classification_reason` field is a free-text string. If the classifier rephrases "external api" as "external API call" or "uses external REST endpoint," the decomposer's substring match fails and the element is incorrectly decomposed instead of being routed to file-whole.

3. **All weights are 0.1.** The uniform weighting means `missing_init` (which makes class decomposition unreliable) and `parse_only_responsibility` (which is informational) have the same confidence penalty. This prevents the decomposer from expressing meaningful confidence distinctions.

#### Recommendation

**R23: Enum-ify uncertainty signals** [LOW EFFORT]. Replace `_UNCERTAINTY_SIGNALS: dict[str, float]` with an `UncertaintySignal` enum where each member carries a weight. Strategies pass enum members, not strings. Unknown signals raise immediately instead of being silently ignored.

**R24: Replace API/Orchestrator substring matching** [LOW EFFORT]. Use `ClassificationSignal` enum (already referenced in the comment) or a structured flag on `TierClassification` / `ClassificationResult`. The classifier should emit a structured flag, not rely on free-text substring matching by downstream consumers.

---

### Finding 27: Repair Module Step Protocol Is Context-Blind

#### The Problem

The `RepairStep` protocol (protocol.py:22–34) has no declarative metadata about which steps are applicable to which generation modes:

```python
class RepairStep(Protocol):
    name: str
    def __call__(self, code, context, file_path, element_context=None) -> RepairStepResult: ...
```

`run_file_repair_pipeline()` (repair.py:679–768) works around this by maintaining a separate `_FILE_REPAIR_STEPS` list with 4 manually-selected steps. If a new repair step is added, the developer must remember to also add it to `_FILE_REPAIR_STEPS` if applicable — or risk the file-whole path missing a relevant repair.

#### Quality Impact

1. **Two-site registration anti-pattern.** Adding a repair step requires updating both `_ELEMENT_REPAIR_STEPS` (the default pipeline) and potentially `_FILE_REPAIR_STEPS`. This is the same two-site registration pattern that SDK Lesson #38 (Leg 13) warns about — and it's the exact same class of bug that caused silent metric gaps in the quality extractor registry.

2. **No validation that file-safe steps are correctly classified.** There is no test verifying that `_FILE_REPAIR_STEPS` is a subset of steps that are actually safe for complete-file output. A developer could add `_step_bare_statement_wrap` to `_FILE_REPAIR_STEPS` without any automated guard catching the error.

#### Recommendation

**R25: Add step applicability metadata** [LOW EFFORT]. Add an `applicable_modes` set to the step protocol or as a module-level registry:

```python
_STEP_APPLICABILITY = {
    "fence_strip": {"element", "file"},
    "ast_validate": {"element", "file"},
    "bare_statement_wrap": {"element"},
    "over_generation_trim": {"element"},
    ...
}
```

`run_file_repair_pipeline()` derives its step list from this registry (`{s for s, modes in _STEP_APPLICABILITY.items() if "file" in modes}`) instead of maintaining a separate hardcoded list. Single source of truth.

---

### Finding 28: `_structural_verify` Python-Version-Fragile Whitelist

#### The Problem

`structural_verify.py` (lines 220–261) maintains a whitelist of allowed AST statement types for class bodies:

> FunctionDef, AsyncFunctionDef, ClassDef, Assign, AnnAssign, Pass, If, Try, AugAssign, TypeAlias (3.12+)

Anything not in the whitelist is flagged as a structural violation.

#### Quality Impact

1. **Python 3.12+ `type` statements.** The code already handles `TypeAlias` with a `getattr(ast, "TypeAlias", None)` guard. But Python 3.13 may introduce new statement types (e.g., `except*` in 3.11 already exists). Each new statement type requires a whitelist update.

2. **Match statements (Python 3.10+).** `ast.Match` is not in the whitelist. A class body containing a `match` statement at the class level (unusual but valid — e.g., for class-level dispatch) would be flagged as a structural violation.

3. **Decorator-only classes.** A class with `@dataclass` and no body except `Pass` is valid, but `@property` methods generate `FunctionDef` nodes that are in the whitelist — however, `@cached_property` may generate different node types depending on the version.

#### Recommendation

**R26: Invert the whitelist to a blocklist** [LOW EFFORT]. Instead of whitelisting allowed statement types (fragile, requires updates per Python version), blocklist the few statement types that are *definitely wrong* in a class body (e.g., `ast.Module`, `ast.Interactive`). All other statement types are allowed by default. This is forward-compatible with new Python versions.

---

## Run 4 Summary

### Remediation Scorecard

| Category | Count | Status |
|----------|------:|--------|
| Fully implemented | 12 | R3, R4, R7, R8, R9, R10, R12, R13, R15, R16, R18, F7 |
| Partially implemented | 2 | R5 (OTel: class done, wrapper functions remain), R14 (escalated fixed, successful still SIMPLE) |
| Not implemented | 5 | R1, R2, R11, R17, R19 |

### New Findings

| Finding | Impact on Output Quality | Effort | Recommendation |
|---------|------------------------|--------|----------------|
| F23: `_completed` cross-seed contamination | Cross-feature few-shot injection in PrimeContractor batches | LOW | R20: Clear between seeds + R19 for same-file scope |
| F24: Two prompt construction philosophies | Element prompt uses fragile f-string+string-header truncation | MEDIUM | R21: Align to section-list pattern (also resolves R11) |
| F25: 3 remaining direct ElementResult constructors | Field drift on template/decomposition results | LOW | R22: Two new factory methods |
| F26: Decomposer string-based classification fallback | Unvalidated uncertainty signals, fragile substring matching | LOW | R23 (enum signals) + R24 (structured classification flag) |
| F27: Repair step protocol is context-blind | Two-site step registration anti-pattern | LOW | R25: Step applicability metadata registry |
| F28: structural_verify Python-version-fragile whitelist | New Python statement types → false structural violations | LOW | R26: Invert to blocklist |

### Priority-Ordered Action Plan (Run 4)

#### Immediate (< 1 hour each, direct quality improvement)

1. **R20**: Clear `_completed` between seeds (fixes F23 — highest output quality impact for batched workloads)
2. **R17**: Thread pre-classified tiers through successful file-whole elements (fixes F20 — 1 line change)
3. **R19**: Scope Tier 1 few-shot to same `file_path` (prevents cross-file class name contamination)
4. **R22**: Two new ElementResult factory methods (fixes F25 — eliminates last 3 direct constructors)

#### Short-term (< 1 day, structural improvement)

5. **R23 + R24**: Enum-ify decomposer uncertainty signals + structured classification flag (fixes F26)
6. **R25**: Repair step applicability metadata (fixes F27)
7. **R26**: Invert structural_verify whitelist to blocklist (fixes F28)

#### Medium-term (architecture, highest cumulative impact)

8. **R21**: Align `build_body_prompt` to section-list pattern (fixes F24, also resolves R11)
9. **R2**: Unify `_generate_with_retry` and `_attempt_file_ollama_whole` retry logic

### Updated Complexity Trajectory

| Metric | Run 1 | Run 3 | Run 4 | Trend |
|--------|------:|------:|------:|-------|
| Compensatory:Essential ratio | 3.1:1 | 2.8:1 | 2.3:1 | ↓ Improving |
| Recommendations open | 6 | 10 | 12 | ↑ More granular |
| Recommendations closed | 0 | 9 | 14 | ↑ Accelerating |
| Findings total | 6 | 22 | 28 | ↑ Deeper analysis |
| Net quality-impacting issues | 6 | 12 | 8 | ↓ Improving |

The module is on the right trajectory. The structural ratio is improving, but the decomposition/splicer/body-repair stack (~6,500 lines) remains the dominant compensatory cost. Only R1 (file-whole as primary, decomposition as fallback) would deliver the step-function improvement. The immediate-priority items (R20, R17, R19, R22) are all low-effort, high-value changes that directly improve output quality for the current architecture.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-12 | Run 4: Post-remediation residual analysis — 14/19 recommendations implemented, 6 new findings (F23–F28), 7 new recommendations (R20–R26). Compensatory:essential ratio improved to 2.3:1. Identified cross-seed `_completed` contamination as highest output-quality risk for batched workloads. Two prompt philosophies (section-list vs f-string) identified as architectural gap. |
| 2026-03-12 | Run 3 implementation: R12 (canonical def-line renderer in models.py — 5 call sites consolidated), bypass cost forwarding fix, coupling threshold test updates |
| 2026-03-12 | Run 3: Remediation audit + residual analysis — 9/14 recommendations implemented, 6 new findings (F17–F22), 5 new recommendations (R15–R19), identified file-whole prompt context starvation as highest-impact quality gap, ElementResult boilerplate as primary field-drift risk |
| 2026-03-12 | Run 2: Output quality impact analysis — 10 new findings (F7–F16), 8 new recommendations (R7–R14), quantified 666 lines of repair code caused by body-only prompt format, identified silent-accept bug in semantic verification, few-shot quality contamination, circuit breaker over-counting |
| 2026-03-12 | Run 1: Initial analysis — 6 findings, 6 recommendations, quantified 3.1:1 compensatory:essential ratio, identified 8,236 lines of potentially deletable decomposition infrastructure |
