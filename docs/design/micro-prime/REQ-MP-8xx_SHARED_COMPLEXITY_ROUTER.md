# REQ-MP-8xx: Shared Complexity Router

Extract Artisan's complexity routing into a shared module and wire it into both PrimeContractorWorkflow and MicroPrimeEngine, creating a unified 4-tier classification system that drives model selection across all code generation paths.

---

## Motivation

Today there are **three independent classification systems** that don't talk to each other:

| System | Location | Tiers | Signal Source | Used By |
|--------|----------|-------|---------------|---------|
| Artisan CMR | `context_seed_handlers.py` | 3 (Tier 1/2/3) | Structural: call graph, manifests, edit mode | IMPLEMENT phase per-chunk |
| Micro Prime | `micro_prime/classifier.py` | 4 (TRIVIAL/SIMPLE/MODERATE/COMPLEX) | Heuristic: params, names, decorators, docstrings | MicroPrimeEngine per-element |
| Prime Contractor | `prime_contractor.py` | 1-10 score | Text: description keywords, dependency count | Feature prioritization only (not routing) |

All three solve the same problem — *"how hard is this code to generate?"* — with different inputs and different outputs. Extracting a shared module lets each workflow leverage the best signals from all three and route to the appropriate model tier consistently.

---

## Target Architecture

```
src/startd8/complexity/
├── __init__.py          # Public API
├── signals.py           # TaskComplexitySignals dataclass (from Artisan)
├── classifier.py        # Shared classification logic
├── config.py            # ComplexityRoutingConfig (threshold tuning)
└── router.py            # Generator/model selection given a tier
```

**Unified tier model:**

| Tier | Local Name | Artisan Equiv | Model Selection | When |
|------|-----------|---------------|-----------------|------|
| TRIVIAL | Tier 0 | — | Template (no LLM) | Element matches template registry |
| SIMPLE | Tier 1 | Tier 1 | Local Ollama (`startd8-coder`) | Greenfield, low blast radius, <150 LOC |
| MODERATE | Tier 2 | Tier 2 | Cloud (Haiku + Sonnet T2) | Default — everything not classified otherwise |
| COMPLEX | Tier 3 | Tier 3 | Premium cloud (Opus) | High blast radius, dynamic dispatch, deep MRO |

---

## Requirements

### REQ-MP-800: TaskComplexitySignals Extraction into Shared Module

Move `TaskComplexitySignals` and `_extract_complexity_signals()` from `context_seed_handlers.py` into `src/startd8/complexity/signals.py`.

**Current location:** `context_seed_handlers.py:4474–4631` + `development.py:374–401`

**Acceptance criteria:**
- `TaskComplexitySignals` dataclass is importable from `startd8.complexity`
- Dataclass is frozen, serializable via `.to_dict()`, all fields have safe defaults
- Existing 11 signal fields preserved: `blast_radius`, `caller_count`, `has_dynamic_dispatch`, `is_closure`, `estimated_loc`, `target_file_count`, `edit_mode`, `mro_depth`, `unresolved_call_count`, `has_cross_file_edges`, `manifest_coverage`
- Never raises — all lookups wrapped in try/except with safe defaults
- Artisan's `_extract_complexity_signals()` is refactored to call the shared extraction function
- Artisan's existing behavior is identical (no regression)

**New extraction functions:**

```python
def extract_signals_from_chunk(chunk, manifest_registry) -> TaskComplexitySignals:
    """Extract signals from an Artisan chunk + manifest registry.
    Port of context_seed_handlers._extract_complexity_signals().
    """

def extract_signals_from_feature(feature, project_root, manifest=None) -> TaskComplexitySignals:
    """Extract signals from a Prime Contractor FeatureSpec.
    New function — mines feature metadata, target files, and optional manifest.
    """

def extract_signals_from_element(element, file_spec, contracts) -> TaskComplexitySignals:
    """Extract signals from a Micro Prime ForwardElementSpec.
    Bridges element-level signals to task-level signal space.
    """
```

---

### REQ-MP-801: Unified Tier Classification

Move `_classify_complexity_tier()` from `context_seed_handlers.py` into `src/startd8/complexity/classifier.py` and extend with TRIVIAL tier.

**Current location:** `context_seed_handlers.py:4634–4687`

**Acceptance criteria:**
- Pure function: `classify_tier(signals, config) -> (Tier, reason_str)`
- Stateless, deterministic, no side effects
- Evaluation order preserved:
  1. **TRIVIAL** check (new): element matches template registry — only applicable for element-level classification
  2. **COMPLEX** triggers (any-one-fires): blast_radius > threshold, has_dynamic_dispatch, edit+high callers, mro_depth > 3, unresolved calls > 2, estimated_loc > threshold, multi-file + cross-edges
  3. **SIMPLE** eligibility (all-must-pass): manifest_coverage = "full", blast_radius = 0, edit_mode = "create", caller_count = 0, no dynamic dispatch, estimated_loc < threshold, single file
  4. **MODERATE**: default fallback
- `reason_str` lists which triggers fired or conditions passed, for observability
- Artisan's existing behavior is identical when called with chunk-extracted signals

---

### REQ-MP-802: ComplexityRoutingConfig

Centralized threshold configuration, replacing scattered constants in `HandlerConfig` and `MicroPrimeConfig`.

**Acceptance criteria:**

```python
@dataclass
class ComplexityRoutingConfig:
    enabled: bool = True                       # Kill switch (False → all MODERATE)
    blast_radius_complex_threshold: int = 5    # Artisan: complexity_blast_radius_tier3
    loc_simple_max: int = 150                  # Artisan: complexity_loc_tier1_max
    loc_complex_min: int = 500                 # Artisan: complexity_loc_tier3_min
    caller_count_complex_threshold: int = 3    # Artisan: complexity_caller_tier3
    mro_depth_complex_threshold: int = 3       # Artisan: hardcoded
    unresolved_calls_complex_threshold: int = 2  # Artisan: hardcoded
    templates_enabled: bool = True             # TRIVIAL tier availability
```

- All current Artisan `HandlerConfig` complexity fields map 1:1
- All current Micro Prime `MicroPrimeConfig` thresholds map in
- `HandlerConfig` retains its fields but delegates to shared config internally
- Config can be constructed from `HandlerConfig` fields, `MicroPrimeConfig` fields, or CLI args

---

### REQ-MP-803: Complexity Router — Generator Selection

Map tiers to generators/models at the workflow level.

**New file:** `src/startd8/complexity/router.py`

**Acceptance criteria:**

```python
class ComplexityRouter:
    """Maps tiers to code generators or agent specs."""

    def __init__(
        self,
        trivial_generator: Optional[CodeGenerator] = None,   # MicroPrime templates
        simple_generator: Optional[CodeGenerator] = None,     # MicroPrime Ollama
        moderate_generator: Optional[CodeGenerator] = None,   # LeadContractor (Haiku+Sonnet)
        complex_generator: Optional[CodeGenerator] = None,    # LeadContractor (Opus)
    ): ...

    def select(self, tier: Tier) -> CodeGenerator:
        """Return the generator for this tier.
        Falls back to moderate_generator if tier-specific generator is None.
        """

    def select_agent_spec(self, tier: Tier) -> str:
        """Return the agent spec string for this tier (Artisan pattern).
        Falls back to moderate agent spec if tier-specific is None.
        """
```

- Null-safe: if a tier's generator is None, falls back to `moderate_generator`
- Artisan usage: `select_agent_spec(tier)` replaces inline tier→drafter routing in `development.py`
- Prime usage: `select(tier)` replaces single `code_generator` in `develop_feature()`
- MicroPrime usage: engine already routes internally — router provides the fallback generator for escalations

---

### REQ-MP-804: Prime Contractor Integration

Wire the shared complexity router into `PrimeContractorWorkflow.develop_feature()`.

**Files modified:** `prime_contractor.py`, `scripts/run_prime_workflow.py`

**Acceptance criteria:**

In `develop_feature()`:
```python
# Before calling generate():
signals = extract_signals_from_feature(feature, self.project_root, self._forward_manifest)
tier, reason = classify_tier(signals, self._complexity_config)
feature.metadata["_complexity_tier"] = tier.value
feature.metadata["_complexity_reason"] = reason
feature.metadata["_complexity_signals"] = signals.to_dict()

generator = self._complexity_router.select(tier)
result = generator.generate(task=feature.description, context=gen_context, target_files=feature.target_files)
```

- When `complexity_routing_enabled = False`, all features use `self.code_generator` (existing behavior)
- When enabled, feature-level signals are extracted and stored in `feature.metadata` for forensic logging
- Generator selection happens per-feature, not once at init
- `_complexity_router` is constructed in `__init__()` or injected from CLI
- Existing `_calculate_complexity_score()` is preserved as a secondary signal (can feed into `estimated_loc` heuristic)

**CLI changes in `run_prime_workflow.py`:**
- `--complexity-routing` flag (default: off for backward compat, until validated)
- `--tier3-agent` flag (agent spec for COMPLEX tier, default: Opus)
- `--micro-prime` flag implies TRIVIAL+SIMPLE tiers route to `MicroPrimeCodeGenerator`

---

### REQ-MP-805: Artisan Refactor to Use Shared Module

Refactor Artisan's complexity routing to delegate to the shared module.

**Files modified:** `context_seed_handlers.py`, `development.py`

**Acceptance criteria:**
- `_extract_complexity_signals()` in `context_seed_handlers.py` delegates to `extract_signals_from_chunk()` from shared module
- `_classify_complexity_tier()` in `context_seed_handlers.py` delegates to `classify_tier()` from shared module
- `HandlerConfig` complexity fields construct a `ComplexityRoutingConfig` internally
- `ArtisanChunkExecutor` model routing uses `ComplexityRouter.select_agent_spec(tier)` instead of inline if/else
- `_decide_t2_refinement()` continues to work with tier values from shared enum
- **Zero behavioral change** — Artisan's existing classification and routing is identical

**Migration approach:**
1. Shared module uses same logic as current Artisan code (copy, not rewrite)
2. Artisan functions become thin wrappers that call shared module
3. Old Artisan constants/thresholds are preserved as defaults in `ComplexityRoutingConfig`
4. Tests pass without modification

---

### REQ-MP-806: Micro Prime Classifier Bridge

Bridge Micro Prime's element-level classification to the shared tier system.

**Files modified:** `micro_prime/classifier.py`

**Acceptance criteria:**
- `classify_element()` uses `extract_signals_from_element()` to get `TaskComplexitySignals`
- Element-level signals map to task-level signal space:
  - `param_count` → no direct mapping (element-specific, kept as secondary signal)
  - `is_async` → feeds into complexity scoring
  - `orchestrator_name` → maps to `has_dynamic_dispatch` or high `blast_radius` heuristic
  - `complex_decorators` → maps to `has_dynamic_dispatch`
  - `docstring_length` → maps to `estimated_loc` heuristic
- TRIVIAL classification remains in Micro Prime (template registry is element-specific)
- SIMPLE/MODERATE/COMPLEX boundaries align with shared thresholds
- Micro Prime's current heuristic scoring is preserved as a refinement layer on top of shared signals

**Not required:** Perfect alignment between element-level and task-level signals. Element-level classification has more granular data (signatures, decorators, param types) that task-level doesn't. The bridge maps what it can and uses Micro Prime's own heuristics for the rest.

---

### REQ-MP-807: Feature-Level Signal Extraction

New function to extract `TaskComplexitySignals` from a Prime Contractor `FeatureSpec`.

**Acceptance criteria:**

`extract_signals_from_feature(feature, project_root, manifest=None) -> TaskComplexitySignals`:

| Signal | Source |
|--------|--------|
| `blast_radius` | Count of existing files that import any `target_file` (static analysis on disk) |
| `caller_count` | From manifest call graph if available, else 0 |
| `has_dynamic_dispatch` | From manifest elements if available, else False |
| `is_closure` | From manifest elements if available, else False |
| `estimated_loc` | From `feature.metadata.get("estimated_loc")` or heuristic from description length |
| `target_file_count` | `len(feature.target_files)` |
| `edit_mode` | "create" if none of `target_files` exist on disk, "edit" if any do |
| `mro_depth` | From manifest elements if available, else 0 |
| `unresolved_call_count` | From manifest call graph if available, else 0 |
| `has_cross_file_edges` | True if `target_file_count > 1` and any file imports another target file |
| `manifest_coverage` | "full" if all target files have manifest entries, "partial"/"none" otherwise |

- When manifest is None, structural signals default to safe values → classification defaults to MODERATE
- When manifest is available, full structural analysis runs (same fidelity as Artisan)
- File system access is scoped to `project_root` (no arbitrary path traversal)
- Never raises — graceful degradation on all I/O errors

---

### REQ-MP-808: Observability

**Acceptance criteria:**
- Tier classification logged at INFO per feature/chunk/element:
  `"Classified {name} as {tier}: {reason}"`
- Signals stored in metadata for forensic inspection:
  `feature.metadata["_complexity_signals"]` / `chunk.metadata["_complexity_signals"]`
- Aggregate metrics per workflow run:
  - Count of features/chunks per tier
  - Tier distribution logged at run completion
- OTel metrics (if active):
  - `complexity.tier_distribution` histogram
  - `complexity.classification_time_ms` (should be negligible — no LLM calls)

---

## Dependency Map

```
REQ-MP-800 (extract signals)
    └── REQ-MP-801 (unified classifier)
            └── REQ-MP-802 (config)
                    └── REQ-MP-803 (router)
                            ├── REQ-MP-804 (Prime integration)
                            ├── REQ-MP-805 (Artisan refactor)
                            └── REQ-MP-806 (Micro Prime bridge)

REQ-MP-807 (feature signal extraction) ── needed by ──→ REQ-MP-804
REQ-MP-808 (observability) — after core wiring works
```

**Recommended implementation order:**
1. **REQ-MP-800 + 801 + 802** — Extract shared module with signals, classifier, config
2. **REQ-MP-805** — Refactor Artisan to use shared module (proves zero-regression)
3. **REQ-MP-803** — Router class
4. **REQ-MP-807** — Feature-level signal extraction
5. **REQ-MP-804** — Prime Contractor integration
6. **REQ-MP-806** — Micro Prime bridge
7. **REQ-MP-808** — Observability

---

## Files Summary

**New files (4):**

| File | LOC Est. | Purpose |
|------|----------|---------|
| `src/startd8/complexity/__init__.py` | ~20 | Public API exports |
| `src/startd8/complexity/signals.py` | ~200 | `TaskComplexitySignals` + 3 extraction functions |
| `src/startd8/complexity/classifier.py` | ~80 | `classify_tier()` pure function |
| `src/startd8/complexity/config.py` | ~40 | `ComplexityRoutingConfig` dataclass |
| `src/startd8/complexity/router.py` | ~60 | `ComplexityRouter` class |

**Modified files (4):**

| File | Change |
|------|--------|
| `src/startd8/contractors/context_seed_handlers.py` | Delegate `_extract_complexity_signals()` and `_classify_complexity_tier()` to shared module |
| `src/startd8/contractors/artisan_phases/development.py` | Move `TaskComplexitySignals`/`TaskComplexityTier` to shared, import from there |
| `src/startd8/contractors/prime_contractor.py` | Add per-feature classification + router selection in `develop_feature()` |
| `src/startd8/micro_prime/classifier.py` | Bridge element signals to shared `TaskComplexitySignals` |

**New test files (3):**

| File | Tests Est. |
|------|-----------|
| `tests/unit/complexity/test_signals.py` | ~20 |
| `tests/unit/complexity/test_classifier.py` | ~15 |
| `tests/unit/complexity/test_router.py` | ~10 |

**Estimated total scope:** ~400 LOC production, ~200 LOC tests, ~45 tests.

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Artisan regression from refactor | REQ-MP-805 requires zero behavioral change; existing Artisan tests must pass unmodified |
| Signal fidelity gap in Prime (no manifest) | Graceful degradation to MODERATE; feature-level signals from disk are still useful (edit_mode, target_file_count, blast_radius) |
| Over-classification to SIMPLE in Prime | Conservative defaults: SIMPLE requires ALL conditions met (same as Artisan Tier 1) |
| Threshold mis-calibration across scopes | Feature-level thresholds may need tuning vs chunk-level; config is externalized for easy adjustment |
| Circular dependency between `complexity/` and `micro_prime/` | `complexity/` has no dependency on `micro_prime/`; bridge in REQ-MP-806 is micro_prime importing complexity, not the reverse |
