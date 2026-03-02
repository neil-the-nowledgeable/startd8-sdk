# Layer 7 — Quick Wins & Acceleration (REQ-MP-7xx)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Planned
> **Date:** 2026-03-01
> **Premise:** Most Micro Prime subsystems are 70-95% already built. This layer identifies the smallest changes that unlock the most value, and defines the compound effects that make their sum greater than their parts.

---

## Overview

The Micro Prime codebase analysis reveals that 7 of 8 major components already exist in some form — as production utilities, experiment script logic, or manifest models. The remaining gap is glue code: ~300 lines of orchestration that wires existing pieces together.

This layer does three things:

1. **Defines existing asset reuse contracts** — what existing code to delegate to, never reimplement
2. **Specifies compound value chains** — how small pieces amplify each other
3. **Establishes an accelerated build order** — sequence that maximizes cumulative value at each step

### Existing Asset Readiness

| Asset | Location | Readiness | Micro Prime Role |
|-------|----------|-----------|-----------------|
| Fence stripping | `utils/code_extraction.extract_code_from_response()` | 100% | Repair Step 1 — zero new code |
| Skeleton rendering | `utils/file_assembler.DeterministicFileAssembler` | 95% | Prompt context + splice target |
| Element models | `forward_manifest.ForwardElementSpec` | 100% | Classification metadata |
| Code manifest enums | `utils/code_manifest.ElementKind`, `Signature`, `Param` | 100% | Template matching, signature reconciliation |
| Heuristic classifier | `scripts/experiment_local_model_routing.py:189-336` | 95% | Tier routing — extract, don't rewrite |
| Few-shot finder | `scripts/experiment_local_model_routing.py:774-817` | 85% | Prompt quality amplifier |
| Indentation normalizer | `scripts/experiment_local_model_routing.py:1007-1058` | 90% | Repair Step 4 — extract, don't rewrite |
| AST validation | `scripts/experiment_local_model_routing.py:983-1004` | 95% | Repair gate — extract, don't rewrite |
| CodeGenerator protocol | `contractors/protocols.CodeGenerator`, `GenerationResult` | 100% | Prime adapter contract |
| Model catalog | `model_catalog.py` (`ModelInfo`, `_MODEL_REGISTRY`) | 70% | Needs `startd8-coder` entry (5 lines) |

---

## Requirements

### REQ-MP-700: Existing Code Delegation Contracts

**Status:** planned
**Priority:** P0

The Micro Prime implementation SHALL delegate to existing production code for capabilities that are already built, rather than reimplementing equivalent logic.

**Mandatory delegation contracts:**

| Capability | Delegate To | Contract |
|-----------|------------|---------|
| Fence stripping | `utils.code_extraction.extract_code_from_response()` | Call directly; never reimplement markdown fence removal |
| Skeleton rendering | `utils.file_assembler.DeterministicFileAssembler.render_file()` | Consume skeleton output as-is; never reconstruct element stubs manually |
| Element metadata | `forward_manifest.ForwardElementSpec` fields | Use `kind`, `signature`, `decorators`, `docstring_hint`, `parent_class` for classification; never re-parse source to infer these |
| Signature rendering | `utils.file_assembler.DeterministicFileAssembler._render_signature()` | Reuse for signature reconciliation (REQ-MP-403); ensures skeleton and repair produce identical signatures |
| Agent resolution | `utils.agent_resolution.resolve_agent_spec("ollama:startd8-coder")` | Use SDK agent resolution for Ollama invocation; never call Ollama HTTP API directly from Micro Prime |

**Rationale:** The experiment script reimplemented stub rendering (`_build_element_stub()`, 56 lines), indentation normalization (`_normalize_indentation()`, 52 lines), and AST validation (`_try_parse()`, 22 lines) because it predated the `DeterministicFileAssembler` and `ForwardManifest` models. The SDK implementation SHALL use the production versions, not the experiment script versions, except where the experiment script logic is more mature (see REQ-MP-701).

**Acceptance criteria:**
- `micro_prime/repair.py` imports `extract_code_from_response` — does not contain regex-based fence stripping
- `micro_prime/prompt_builder.py` uses `DeterministicFileAssembler` output — does not reconstruct element stubs from raw fields
- `micro_prime/engine.py` calls `resolve_agent_spec()` — does not construct HTTP requests to Ollama
- No delegation target is modified to accommodate Micro Prime (consume-only contracts)

---

### REQ-MP-701: Experiment Script Extraction Map

**Status:** planned
**Priority:** P0

Functions in the experiment script (`scripts/experiment_local_model_routing.py`) that have been validated across Rounds 1-2 SHALL be extracted to the `micro_prime` package rather than rewritten.

**Extraction targets:**

| Function | Lines | Extract To | Changes Required |
|----------|-------|-----------|-----------------|
| `classify_element_heuristic()` | 189-336 (148 lines) | `micro_prime/classifier.py` | Move signal constants to module-level; add `MicroPrimeTier` enum return type (TRIVIAL/SIMPLE/MODERATE/COMPLEX vs current SIMPLE/MODERATE/COMPLEX); integrate template registry check as first gate |
| `_try_parse()` | 983-1004 (22 lines) | `micro_prime/repair.py` | Rename to `is_syntactically_valid()`; no logic changes |
| `_normalize_indentation()` | 1007-1058 (52 lines) | `micro_prime/repair.py` | Add skeleton-aware strategy as priority (REQ-MP-402); keep existing 5 heuristic strategies as fallback |
| `_extract_syntax_error()` | 1061-1067 (7 lines) | `micro_prime/repair.py` | No changes |
| `_find_few_shot_examples()` | 774-817 (44 lines) | `micro_prime/prompt_builder.py` | Adapt from `ClassifiedElement` list to `ElementResult` list; keep tiered priority (same-class > same-file > same-kind) |
| `_estimate_body_lines()` | 756-771 (16 lines) | `micro_prime/prompt_builder.py` | No changes |
| `collect_elements()` | 1263-1292 (30 lines) | `micro_prime/classifier.py` | No changes |

**Total: ~319 lines of validated logic, extracted not rewritten.**

**Functions NOT extracted** (too tightly coupled to experiment orchestration or superseded by SDK equivalents):

| Function | Reason Not Extracted |
|----------|---------------------|
| `_build_element_stub()` | Superseded by `DeterministicFileAssembler._render_element()` |
| `_build_ollama_prompt()` | Rewritten as `micro_prime/prompt_builder.py` with skeleton-first approach (REQ-MP-200) |
| `_build_constant_prompt()` | Folded into prompt builder with body-type dispatch |
| `generate_with_ollama()` | Superseded by `resolve_agent_spec()` + SDK agent call pattern |
| `verify_with_sonnet()` | Retained in experiment script; SDK uses existing verification paths |
| `run_experiment()` | Experiment orchestrator; not an SDK component |
| `synthesize_manifest()` | Retained in experiment script; SDK receives manifests from upstream phases |

**Acceptance criteria:**
- Extracted functions retain their validated behavior (unit tests compare output against experiment script for same inputs)
- Experiment script updated to import from `micro_prime` package instead of maintaining duplicate logic
- No extracted function exceeds 20% diff from its experiment script source (measured by line-level diff)

---

### REQ-MP-702: splice_body() on DeterministicFileAssembler

**Status:** planned
**Priority:** P0
**Extends:** REQ-MP-202 (Body Splicing), REQ-MP-505 (Skeleton Preservation)
**Modifies:** `src/startd8/utils/file_assembler.py`

The `DeterministicFileAssembler` SHALL expose a `splice_body()` method that replaces a specific element's `raise NotImplementedError` stub with generated body code.

**Why this is a keystone:** The assembler already renders skeletons with `raise NotImplementedError` at known indent levels (`file_assembler.py:408`). Adding a method to replace a specific stub is ~25 lines that bridges generation output to file output. Without it, no generated body (template, local model, or cloud) can be integrated. With it, all tiers share a common insertion mechanism.

**Interface:**

```python
def splice_body(
    self,
    skeleton_source: str,
    element_name: str,
    body: str,
    parent_class: Optional[str] = None,
) -> str:
    """Replace the raise NotImplementedError stub for element_name with body.

    Args:
        skeleton_source: The rendered skeleton file content.
        element_name: Name of the function/method/constant to fill.
        body: The generated body code (will be re-indented to match stub level).
        parent_class: If element is a method, the containing class name.

    Returns:
        Updated skeleton source with the body spliced in.

    Raises:
        ValueError: If element_name not found in skeleton or result fails ast.parse().
    """
```

**Algorithm:**

1. Parse `skeleton_source` via `ast.parse()` to locate the target element
2. Find the `Raise(NotImplementedError)` node within the element's body
3. Determine the stub's indentation level from the source line
4. Dedent the generated body, re-indent to match stub level
5. Replace the stub line(s) with the re-indented body using source line offsets
6. Validate the result via `ast.parse()`; raise `ValueError` on failure

**Stub formats to handle:**

| Element Kind | Stub Pattern | Example |
|-------------|-------------|---------|
| Function/Method | `raise NotImplementedError` | `    raise NotImplementedError` (4 or 8 spaces) |
| Constant/Variable | `...` (Ellipsis) | `TIMEOUT = ...` |
| Property | `raise NotImplementedError` (within `@property def`) | Same as method |

**Acceptance criteria:**
- A function body spliced into a method stub produces a valid file (`ast.parse()` passes)
- A constant value spliced into an ellipsis stub produces a valid file
- Splicing preserves all other elements, imports, `__all__`, and class structure unchanged
- Multiple sequential splices into the same skeleton produce a valid file (for multi-element files)
- Incorrect indentation in the body input is corrected to match the stub's indent level
- Method on the existing `DeterministicFileAssembler` class — not a separate module

---

### REQ-MP-703: Non-Destructive Repair Step Decorator

**Status:** planned
**Priority:** P0
**Implements:** REQ-MP-406 (Non-Destructive Guarantee)

The repair pipeline SHALL provide a `@repair_step` decorator that wraps any repair function with before/after AST validation and automatic rollback. This enables incremental delivery: ship with 2 steps, add 5 more later, each independently safe.

**Interface:**

```python
def repair_step(name: str):
    """Decorator that enforces the non-destructive guarantee for a repair step.

    Wraps the decorated function with:
    1. Pre-check: is input code syntactically valid?
    2. Execute: call the repair function
    3. Post-check: if input was valid and output is invalid, rollback to input
    4. Report: return (code, modified: bool, metrics: dict)
    """
```

**Decorated function contract:**

```python
@repair_step("indentation_normalize")
def normalize_indentation(
    code: str,
    target: ForwardElementSpec,
    skeleton_source: Optional[str] = None,
) -> str:
    """Each repair function takes code + context, returns repaired code."""
    ...
```

**Rollback logic:**

```python
def _apply_step(code: str, step_fn, *args, **kwargs) -> tuple[str, bool, dict]:
    was_valid = _is_syntactically_valid(code)
    repaired = step_fn(code, *args, **kwargs)

    if repaired == code:
        return code, False, {}                        # No change

    if was_valid and not _is_syntactically_valid(repaired):
        return code, False, {"rolled_back": True}     # Rollback

    return repaired, True, {}                         # Applied
```

**Why this enables incremental delivery:**
- Phase 1: Ship repair pipeline with fence stripping + indentation normalization (2 steps)
- Phase 2: Add over-generation trim + bare statement wrap (4 steps)
- Phase 3: Add signature reconciliation + import completion (6 steps)
- At every phase, the decorator guarantees no step can make things worse
- Each step can be feature-flagged independently via the pipeline's step list

**Acceptance criteria:**
- A repair step that turns valid Python into invalid Python has its changes discarded
- A repair step that turns invalid Python into valid Python has its changes kept
- A repair step that turns invalid Python into different invalid Python has its changes kept (not worse)
- Per-step metrics (`modified`, `rolled_back`, step `name`) are collected for REQ-MP-601
- Adding a new repair step to the pipeline requires only: write the function, decorate with `@repair_step("name")`, append to the step list

---

### REQ-MP-704: Compound Value Chain — Template-to-Few-Shot Pipeline

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-300 (Template Registry), REQ-MP-205 (Few-Shot Examples), REQ-MP-505 (Processing Order)

TRIVIAL elements filled by the template registry SHALL be immediately available as few-shot examples for subsequent SIMPLE generation within the same file. This creates a self-reinforcing quality cycle where each success improves the next generation.

**Value chain:**

```
Template Registry fills TRIVIAL elements (100% correct, $0, <1ms)
  │
  └─ Filled bodies become few-shot examples (REQ-MP-205)
       │
       └─ SIMPLE generation quality improves (~15-25% higher pass rate with examples)
            │
            └─ More SIMPLE elements pass verification
                 │
                 └─ Successful SIMPLE bodies become additional few-shot examples
                      │
                      └─ Later SIMPLE elements benefit from richer example set
                           │
                           └─ Fewer escalations to cloud → cost savings compound
```

**Processing order requirement:**

Within the Micro Prime engine's per-file processing, elements SHALL be processed in this order:

1. **TRIVIAL** — Template registry (deterministic, always correct)
2. **SIMPLE** — Local model with few-shot examples accumulated from step 1 + prior step 2 successes
3. **MODERATE/COMPLEX** — Returned as `needs_cloud` (but receive partially-filled skeleton with TRIVIAL + SIMPLE bodies as in-context examples)

This refines REQ-MP-505's inter-tier ordering with the specific intra-tier ordering that maximizes few-shot accumulation.

**Projected impact (from Round 2 data):**
- Without few-shot: 33% SIMPLE verification rate (8/24 elements)
- With few-shot from templates: projected 42-50% (templates provide the first correct examples in each file)
- With accumulated few-shot: projected 50-60% (each SIMPLE success provides examples for remaining SIMPLE elements)

**Acceptance criteria:**
- A file with 2 TRIVIAL + 5 SIMPLE elements: the first SIMPLE element receives 2 few-shot examples (from the 2 TRIVIAL bodies); the third SIMPLE element receives up to 2 examples chosen from TRIVIAL + first two SIMPLE successes
- Processing order is deterministic: TRIVIAL elements first (alphabetical within tier), then SIMPLE (alphabetical)
- Few-shot example selection follows the priority from REQ-MP-205: same-class > same-file > same-kind
- If no TRIVIAL elements exist in a file, SIMPLE elements still process (with 0 initial examples, accumulating from their own successes)

---

### REQ-MP-705: Accelerated Build Order

**Status:** planned
**Priority:** P1

The implementation SHALL follow a prioritized build order that maximizes cumulative delivered value at each step, enabling early integration testing and incremental rollout.

**Build sequence:**

| Step | Deliverable | Effort | Cumulative Value | Requirements Addressed |
|------|------------|--------|-----------------|----------------------|
| 1 | `splice_body()` on `DeterministicFileAssembler` | ~25 lines | Unblocks all body insertion; enables template, local model, and cloud output to share one integration path | REQ-MP-702, REQ-MP-202, REQ-MP-505 |
| 2 | Template registry (TRIVIAL tier) | ~100 lines | 10-15% of elements at $0, 100% correct; produces first few-shot examples | REQ-MP-300–304 |
| 3 | `startd8-coder` model catalog entry | ~12 lines | SDK-native Ollama model resolution; `resolve_agent_spec("ollama:startd8-coder")` works | REQ-MP-104 |
| 4 | `@repair_step` decorator + fence stripping + indentation normalization | ~90 lines | Repair pipeline MVP handling the 2 most common failure modes (fences: 100% of raw output; indentation: 53% of Round 1 failures) | REQ-MP-703, REQ-MP-400, REQ-MP-402, REQ-MP-406 |
| 5 | Heuristic classifier extraction | ~170 lines (148 extracted + 22 adapter) | Zero-cost tier routing decisions for all elements | REQ-MP-701, REQ-MP-500, REQ-MP-501 |
| 6 | Few-shot wiring + compound chain | ~60 lines | Quality amplifier: TRIVIAL bodies as examples for SIMPLE generation | REQ-MP-704, REQ-MP-205 |
| 7 | Element-level import gate | ~30 lines on top of classifier | Recovers 2-3 elements per seed over-classified by file-level gate | REQ-MP-511 |
| 8 | Remaining repair steps (over-gen trim, bare wrap, sig reconcile, import complete) | ~200 lines | Full repair pipeline covering all 6 failure modes | REQ-MP-401, REQ-MP-403, REQ-MP-404, REQ-MP-407 |

**Cumulative value at key milestones:**

| After Step | What Works | Elements Handled Locally | Cloud Cost Reduction |
|-----------|-----------|------------------------|---------------------|
| 2 | Templates + splicing | TRIVIAL only (~3-5 per seed) | ~10-15% |
| 4 | Templates + basic repair | TRIVIAL + SIMPLE (with 2-step repair) | ~20-25% |
| 6 | Templates + repair + few-shot | TRIVIAL + SIMPLE (with quality amplification) | ~30-40% |
| 8 | Full pipeline | TRIVIAL + SIMPLE (full repair + verification) | ~35-50% |

**Integration test gates:**

| After Step | Test |
|-----------|------|
| 1 | `splice_body()` round-trip: render skeleton → splice body → `ast.parse()` passes |
| 2 | Template registry: match + splice + validate for config constants and `__init__` methods |
| 4 | Repair pipeline MVP: raw Ollama output → fence strip → indent normalize → valid Python |
| 6 | Compound chain: file with TRIVIAL + SIMPLE → TRIVIAL fills → SIMPLE uses few-shot → higher pass rate |

**Acceptance criteria:**
- Each step is independently shippable (no step depends on a later step)
- Each step is tested before proceeding (integration test gate passes)
- Steps 1-4 can be completed within the existing `DeterministicFileAssembler` and `micro_prime/repair.py` files (2 files touched)
- Steps 5-7 add `micro_prime/classifier.py` and `micro_prime/prompt_builder.py` (2 new files)
- The experiment script can exercise each step individually via `--steps` flag for A/B comparison

---

### REQ-MP-706: Incremental Repair Pipeline Delivery

**Status:** planned
**Priority:** P1
**Depends on:** REQ-MP-703 (`@repair_step` decorator)
**Refines:** REQ-MP-400 (Repair Pipeline Structure)

The repair pipeline SHALL be designed for incremental delivery. Each step is independently deployable, testable, and feature-flaggable.

**Delivery phases:**

| Phase | Steps Included | Failure Modes Addressed | Expected Recovery |
|-------|---------------|------------------------|-------------------|
| MVP | Fence stripping, Indentation normalization | Markdown fences (100% of raw output), Whitespace mangling (53% of Round 1 failures) | ~60% of syntax failures recovered |
| Phase 2 | + Over-generation trim, + Bare statement wrap | Extra functions/classes after target (10% of output), Body-only output without `def` line | ~80% of syntax failures recovered |
| Phase 3 | + Signature reconciliation, + Import completion | Param renamed/dropped (5-10%), Missing imports in generated code (15-20%) | ~90% of syntax failures recovered |

**Feature flag:**

```python
class RepairConfig:
    enabled_steps: list[str] = field(default_factory=lambda: [
        "fence_strip",
        "indentation_normalize",
    ])  # MVP default — add steps as validated
```

**Acceptance criteria:**
- Pipeline with only MVP steps (fence strip + indent) produces a measurable improvement over raw model output
- Adding a new step requires: (1) write function, (2) add `@repair_step` decorator, (3) append name to `enabled_steps` default
- Removing a step requires: (1) remove name from `enabled_steps` — no code changes
- Each phase's recovery rate is measured via experiment script before advancing to the next phase

---

### REQ-MP-707: Model Catalog Ollama Provider Section

**Status:** planned
**Priority:** P1
**Implements:** REQ-MP-104 (Model Registry Entry)
**Modifies:** `src/startd8/model_catalog.py`

The model catalog SHALL include an Ollama provider section with the `startd8-coder` entry. This is ~12 lines total: 2 lines for the `Models` constant, 5 lines for the `_MODEL_REGISTRY` entry, and 5 lines for the `get_latest_model()` tier mapping.

**Exact additions:**

In `Models` class:
```python
# Ollama (local)
OLLAMA_STARTD8_CODER = "ollama:startd8-coder"
```

In `_MODEL_REGISTRY`:
```python
"startd8-coder": ModelInfo(
    provider="ollama",
    model_id="startd8-coder",
    tier="fast",
    capabilities={"text", "code"},
),
```

In `get_latest_model()` tier mapping:
```python
"ollama": {
    "fast": Models.OLLAMA_STARTD8_CODER,
    "balanced": Models.OLLAMA_STARTD8_CODER,
},
```

**Why this matters beyond REQ-MP-104:** The model catalog is the SDK's single source of truth for model capabilities. Without this entry, `resolve_agent_spec("ollama:startd8-coder")` cannot find default parameters, the Prime Contractor cannot route to the local model via its model selection logic, and preflight checks cannot validate model availability through standard SDK paths.

**Acceptance criteria:**
- `resolve_agent_spec("ollama:startd8-coder")` returns a valid agent with `max_tokens=512`
- `get_latest_model("ollama", "fast")` returns `"ollama:startd8-coder"`
- `ModelInfo` entry has `capabilities={"text", "code"}` (no "vision" or "reasoning")
- Existing model catalog tests pass without modification

---

### REQ-MP-708: Element-Level Import Gate Refinement

**Status:** planned
**Priority:** P2
**Refines:** REQ-MP-511 (Per-Element API Dependency Analysis)

The per-element import gate (REQ-MP-511 Pass 2) SHALL use three signals to determine whether a specific element uses external APIs, even when its file imports them.

**Signals:**

| Signal | Check | Weight |
|--------|-------|--------|
| Binding constraints | Element's `[BINDING]` constraints reference external package names | +2 per match |
| Parameter types | Element's signature params have types from external packages (e.g., `grpc.ServicerContext`) | +2 per match |
| Name patterns | Element name contains API-specific patterns (e.g., `Serve`, `Handle`, `Request`) combined with external package in file imports | +1 per match |

**Override logic:**

```python
def _element_uses_external_api(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    external_packages: set[str],
) -> bool:
    """Check if THIS element (not just its file) uses external APIs."""
    # File doesn't import external packages → element is safe
    file_externals = _file_external_packages(file_spec, external_packages)
    if not file_externals:
        return False

    # Check element-specific signals
    score = 0
    for constraint in element.binding_constraints:
        if any(pkg in constraint.lower() for pkg in file_externals):
            score += 2

    if element.signature:
        for param in element.signature.params:
            if param.annotation and any(pkg in param.annotation for pkg in file_externals):
                score += 2

    return score > 0
```

**Round 2 data that motivates this:**

| Element | File Imports | Element Uses External API? | File-Level Gate | Element-Level Gate |
|---------|-------------|---------------------------|-----------------|-------------------|
| `HealthCheck.Check` | `grpc` | No — simple return dict | BLOCK (wrong) | PASS (correct) |
| `WebsiteUser.viewCart` | `locust` | No — simple HTTP call with `self.client` | BLOCK (wrong) | PASS (correct) |
| `WebsiteUser.on_start` | `locust` | Yes — uses `locust.HttpUser` lifecycle | BLOCK (correct) | BLOCK (correct) |

**Projected impact:** Routes ~14 elements locally (vs 6 with file-level only) at ~71% verified rate (vs 33%).

**Acceptance criteria:**
- Elements in external-import files whose signatures and constraints don't reference those packages are classified as SIMPLE
- Elements whose `[BINDING]` constraints explicitly name external packages are classified as MODERATE
- The gate recovers at least 2 additional elements per seed compared to file-level only

---

## Compound Value Chains

### Chain 1: Template → Few-Shot → Quality Amplification

```
REQ-MP-300 (Template Registry)
  → REQ-MP-702 (splice_body)
    → REQ-MP-704 (compound chain)
      → REQ-MP-205 (few-shot examples)
        → Higher SIMPLE pass rate
          → More few-shot examples
            → Even higher pass rate (virtuous cycle)
```

**Each template match produces:**
- One correct body at $0 cost (direct value)
- One few-shot example for SIMPLE generation (amplified value)
- One filled stub that cloud models see as in-context example (cascading value)

### Chain 2: Repair Decorator → Incremental Steps → Progressive Recovery

```
REQ-MP-703 (@repair_step decorator)
  → REQ-MP-706 (incremental delivery)
    → Ship MVP with 2 steps
      → Measure recovery rate
        → Add 2 more steps
          → Measure improvement
            → Full pipeline (6 steps)
```

**Each decorator-wrapped step produces:**
- Guaranteed non-destructive behavior (safe to ship any subset)
- Per-step attribution metrics (REQ-MP-601) for ROI measurement
- Incremental recovery rate improvement (compound)

### Chain 3: Classifier → Gate → Cost Savings

```
REQ-MP-701 (classifier extraction)
  → REQ-MP-500 (four-tier routing)
    → REQ-MP-708 (element-level gate)
      → More elements correctly routed locally
        → Fewer unnecessary cloud calls
          → Cost savings even before repair pipeline is complete
```

---

## Integration Checklist

| Step | File | Change | Lines |
|------|------|--------|-------|
| 1 | `utils/file_assembler.py` | Add `splice_body()` method | ~25 |
| 2 | `micro_prime/templates.py` | New: template registry | ~100 |
| 3 | `model_catalog.py` | Add Ollama provider section + `startd8-coder` | ~12 |
| 4 | `micro_prime/repair.py` | New: `@repair_step` decorator + fence strip + indent normalize | ~90 |
| 5 | `micro_prime/classifier.py` | New: extracted heuristic classifier + `collect_elements()` | ~170 |
| 6 | `micro_prime/prompt_builder.py` | New: few-shot finder + body line estimator | ~60 |
| 7 | `micro_prime/classifier.py` | Add element-level import gate (Pass 2) | ~30 |
| 8 | `micro_prime/repair.py` | Add remaining 4 repair steps | ~200 |
| **Total** | | | **~687** |
