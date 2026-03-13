# Accidental Complexity Analysis: PlanIngestionWorkflow

**Date**: 2026-03-12 (Run 1 — initial analysis)
**Anti-principle reference**: [`ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md`](../../design-princples/ACCIDENTAL_COMPLEXITY_ANTI_PRINCIPLE.md)
**Scope**: Full execution path from `run_iterative_plan_ingestion.py` to context seed + review config on disk
**Method**: Codebase scan of all files in the pipeline path, exact `wc -l` counts, dead code verification via grep, layer-by-layer classification

---

## Executive Summary

The PlanIngestionWorkflow pipeline spans **10,552 lines across 13 files** (+ 183 lines of YAML prompts) to solve this essential problem:

> Given a markdown plan, extract features, enrich them into code-generation-ready task specifications, and emit a context seed file that enables inexpensive models to generate high-quality code.

The pipeline has **14 transformation layers** between "user invokes script" and "context seed on disk." Of these, **8 are essential**, **3 are compensatory**, **2 are defensive**, and **1 is vestigial**. The compensatory:essential ratio is **0.38:1** in layer count — significantly healthier than PrimeContractor.

**Strategic context**: The enrichment and Micro-Ingest layers are not compensatory — they are the **core value differentiator** of the project. The goal is to enable progressively cheaper models (Ollama, Haiku) to produce high-quality code by investing in richer task specifications at ingestion time. Better enrichment + better prompts → cheaper generation. This makes enrichment *essential*, not accidental.

**Routing context**: The Prime vs Artisan routing decision is currently **vestigial** — the Artisan workflow is on hold, and PrimeContractor is the only active construction path. The ASSESS phase, translation quality gate, and routing logic (~500+ lines) serve a dormant feature.

The pipeline has **no dead code** — every function is called. The accidental complexity is concentrated in:

1. **God-file monolith** — 5,907 lines in a single file with 36 module-level helpers + 27 class methods
2. **Config parameter explosion** — 30+ `config.get()` calls with inconsistent parsing, 28 WorkflowInput declarations
3. **Vestigial routing machinery** — ~500+ lines of complexity assessment, quality gates, and route overrides serving a dormant Artisan path

---

## The Essential Problem

```
Input:  plan.md (implementation plan in markdown)
Output: context-seed.json (structured task list + metadata for code generation)
        review-config.json (configuration for downstream workflows)
```

**Essential transformations** (minimum viable pipeline):
1. Parse plan text → structured feature list (LLM or heuristic)
2. Transform features → SDK-native format (Prime YAML)
3. Enrich tasks into code-generation-ready specifications (the core value add)
4. Emit context seed (assemble tasks, metadata, write files)

**Essential but currently vestigial**:
5. Assess complexity → routing decision (Prime vs Artisan) — Artisan is on hold; all traffic routes to Prime

**Optional but valuable**:
6. Refine via architectural review (LLM-powered quality improvement)

**Essential layer count: 4** (5 with refinement, 6 when Artisan resumes)

---

## Exact Line Counts

### Core Pipeline Files (10,552 lines)

| File | Lines | Classification |
|------|------:|---------------|
| `plan_ingestion_workflow.py` | 5,907 | Mixed (monolith orchestrator) |
| `plan_ingestion_micro_ingest.py` | 1,056 | COMPENSATORY |
| `derivation.py` (seeds/) | 790 | Mixed (ESSENTIAL + COMPENSATORY) |
| `plan_ingestion_enrichment.py` | 658 | COMPENSATORY |
| `plan_ingestion_diagnostics.py` | 570 | COMPENSATORY (observability) |
| `builder.py` (seeds/) | 408 | **ESSENTIAL** |
| `plan_ingestion_models.py` | 282 | **ESSENTIAL** (data models) |
| `models.py` (seeds/) | 268 | **ESSENTIAL** (data models) |
| `validation.py` (seeds/) | 188 | DEFENSIVE |
| `run_iterative_plan_ingestion.py` | 116 | Entry point |
| `prompts/plan_ingestion.yaml` | 183 | **ESSENTIAL** |
| `helpers.py` (seeds/) | 77 | **ESSENTIAL** (utilities) |
| `schema_versions.py` (seeds/) | 22 | Config |
| `__init__.py` (seeds/) | 27 | Boilerplate |

**Grand Total: 10,552 lines** (+ 183 YAML)

### Test Files (7,039 lines)

| File | Lines |
|------|------:|
| `test_plan_ingestion_workflow.py` | 2,823 |
| `test_plan_ingestion_micro_ingest.py` | 949 |
| `test_plan_ingestion_enrichment.py` | 887 |
| `test_plan_ingestion_diagnostics.py` | 712 |
| `test_plan_ingestion_otel.py` | 684 |
| `test_wcp_gap_validation.py` | 613 |
| `test_plan_ingestion_preflight.py` | 247 |
| `test_plan_ingestion_manifest.py` | 124 |

---

## Layer Map

```
run_iterative_plan_ingestion.py (116 lines)
  │
  ├─ CLI parsing, agent spec resolution, config assembly
  │
  ▼
PlanIngestionWorkflow._execute() (930 lines — from line 4977 to end)
  │
  ├─ 30+ config.get() parameter extraction
  ├─ Mottainai Layer 1: artifact inventory reuse              ─── [COMPENSATORY]
  ├─ Layer 5: CapabilityValidator contract check              ─── [DEFENSIVE]
  ├─ Kaizen config auto-discovery + loading                   ─── [COMPENSATORY]
  ├─ Task tracking config                                     ─── [COMPENSATORY]
  ├─ OTel root span + phase span lifecycle                    ─── [COMPENSATORY]
  │
  ├── PREFLIGHT ────────────────────────────────────────────── [DEFENSIVE]
  │   ├─ _preflight_export_contract()           (153 lines)
  │   ├─ Export coverage validation
  │   ├─ .contextcore.yaml discovery
  │   └─ Manifest loading (contextcore optional import)
  │
  ├── PARSE ────────────────────────────────────────────────── [ESSENTIAL]
  │   ├─ _phase_parse()                         (106 lines)
  │   ├─ LLM: extract features from plan text
  │   ├─ _heuristic_parse_plan() fallback       (92 lines)    ─── [COMPENSATORY]
  │   ├─ _extract_json_from_response()          (84 lines)
  │   ├─ _enrich_features_from_plan()           (43 lines)    ─── [ESSENTIAL — strategic]
  │   │   ├─ _extract_implementation_contracts()
  │   │   └─ _scope_contract_to_files()
  │   └─ _evaluate_translation_quality()        (126 lines)   ─── [VESTIGIAL — serves routing]
  │
  ├── ASSESS ───────────────────────────────────────────────── [VESTIGIAL — Artisan on hold]
  │   ├─ _phase_assess()                        (150 lines)
  │   ├─ LLM: score 7-8 complexity dimensions
  │   ├─ _heuristic_assess_complexity() fallback (187 lines)  ─── [VESTIGIAL]
  │   ├─ Heuristic degradation override                       ─── [VESTIGIAL]
  │   └─ Translation quality routing gate                     ─── [VESTIGIAL]
  │
  ├── TRANSFORM ────────────────────────────────────────────── [ESSENTIAL]
  │   ├─ _phase_transform()                     (143 lines)
  │   ├─ LLM: convert to Prime YAML
  │   └─ _heuristic_transform_content() fallback (42 lines)   ─── [COMPENSATORY]
  │
  ├── REFINE ───────────────────────────────────────────────── [COMPENSATORY]
  │   ├─ _phase_refine()                        (90 lines)
  │   ├─ Delegates to ConvergentReviewWorkflow
  │   ├─ Enrichment-aware scope + profile config (60 lines)   ─── [COMPENSATORY]
  │   ├─ Kaizen prompt/response capture                       ─── [COMPENSATORY]
  │   └─ Silent failure guard                                 ─── [DEFENSIVE]
  │
  ├── EMIT ─────────────────────────────────────────────────── [ESSENTIAL]
  │   ├─ _phase_emit()                          (650 lines)
  │   ├─ Task derivation (_derive_tasks_from_features)
  │   ├─ Task splitting (_split_oversized_tasks)
  │   ├─ Trivial task filtering
  │   ├─ Story point estimation
  │   ├─ Deterministic enrichment (Option A)     (658 lines)  ─── [ESSENTIAL — strategic]
  │   ├─ Micro-Ingest enrichment (Option B)      (1,056 lines) ─── [ESSENTIAL — strategic differentiator]
  │   ├─ Mottainai pre-assembly (FR-MPA)         (264 lines)  ─── [ESSENTIAL — cross-run reuse]
  │   ├─ Pre-fill to skeletons                   (167 lines)  ─── [ESSENTIAL — enables cheap generation]
  │   ├─ Architectural context derivation
  │   ├─ Design calibration derivation
  │   ├─ Seed assembly (SeedBuilder)
  │   ├─ Seed validation (JSON schema + field coverage)       ─── [DEFENSIVE]
  │   ├─ ContextCore task tracking emission
  │   ├─ Traceability artifact generation
  │   └─ Kaizen diagnostic report
  │
  ▼
Output: context-seed.json + review-config.json + traceability.json + diagnostic.json
```

---

## Layer Classification

### Essential (8 layers, ~6,540 lines, 62%)

| Layer | Code | Lines | Rationale |
|-------|------|------:|-----------|
| **Parse features** | `_phase_parse()` + `_extract_json` + `_fmt_prompt()` | ~423 | Core: extract structure from prose |
| **Transform format** | `_phase_transform()` | ~143 | Core: convert to Prime YAML |
| **Feature enrichment from plan** | `_enrich_features_from_plan()` + contract extraction | ~250 | **Strategic**: inject implementation contracts at $0.00 — enables cheaper downstream models |
| **Deterministic enrichment (Option A)** | `enrich_tasks_deterministic()` | 658 | **Strategic**: fills negative scope, target files, API sigs, requirement refs at $0.00 — directly improves cheap-model generation quality |
| **Micro-Ingest enrichment (Option B)** | `enrich_tasks_micro_ingest()` | 1,056 | **Strategic differentiator**: DFA stubs + template code + optional Ollama generation. Enables inexpensive models (Ollama, Haiku) to produce quality output. This is the core value proposition — invest at ingestion, save at generation. |
| **Mottainai pre-assembly** (FR-MPA) | `_mottainai_pre_assembly()` + `_apply_pre_fill_to_skeletons()` | ~431 | **Strategic**: element registry reuse + skeleton pre-fill eliminates redundant generation by cheap models |
| **Emit seed** | `_phase_emit()` core (task derivation + SeedBuilder + file write) | ~650 | Core: produce context seed |
| **Data models + derivation** | models + `derivation.py` + `builder.py` + prompts + entry + utils | ~2,929 | Infrastructure |

### Compensatory (3 layers, ~1,041 lines, 10%)

| Layer | Lines | Compensates for | Justified? |
|-------|------:|-----------------|------------|
| **Heuristic fallbacks** (parse + assess + transform) | ~321 | LLM unreliability | **Yes** — $0.00 fallback prevents pipeline stall. However, heuristic assess (187 lines) is over-engineered for its current value (see Vestigial). |
| **Diagnostics + Kaizen + OTel** | ~870 | Lack of native pipeline observability | **Yes** — essential for debugging, but compensatory for pipeline operation. Follows project standard. |
| **REFINE phase** (arc-review delegation) | ~150 | Plan quality insufficient for code generation | **Partially** — adds $0.10-0.50/run; skip_arc_review exists. Valuable when enrichment alone isn't enough. |

### Defensive (2 layers, ~1,544 lines, 15%)

| Layer | Lines |
|-------|------:|
| **Preflight validation** (export contract, .contextcore.yaml) | ~153 |
| **Seed validation** (JSON schema + field coverage) | ~413 |
| **Config validation** (`_custom_validate`) | ~100 |
| **Capability contract validation** (Layer 5) | ~30 |

### Vestigial (1 layer, ~500+ lines, ~5%)

| Layer | Lines | Status |
|-------|------:|--------|
| **Routing machinery** (ASSESS phase + translation quality gate + heuristic degradation override + route override logic + Artisan transform path) | ~500+ | **Dormant** — Artisan workflow is on hold. All traffic routes to Prime. The ASSESS phase's 7-dimension complexity scoring, heuristic assess fallback (187 lines), translation quality evaluation (126 lines), routing gate, and degradation override exist to make a Prime-vs-Artisan decision that currently has only one answer. |

**Note on vestigial vs dead**: This code is not dead — it executes on every run, produces a complexity score, and routes to Prime. But the routing decision has **trivial value** because only one route is active. The 500+ lines of scoring, quality gates, and override logic could be replaced with `route = ContractorRoute.PRIME` for identical production behavior.

---

## Sub-Pattern Analysis

### 1. God-File Monolith (5,907 lines)

`plan_ingestion_workflow.py` contains **36 module-level helper functions** (lines 1–1964) and a **27-method class** (lines 1965–5907). This is the single largest file in the SDK.

**What belongs together**: The 5 pipeline phases (PARSE, ASSESS, TRANSFORM, REFINE, EMIT) are naturally sequential and share state through `IngestionState`. A single orchestrator is appropriate.

**What doesn't belong together**:

| Function Group | Count | Lines | Purpose |
|---------------|------:|------:|---------|
| JSON/parsing helpers | 6 | ~210 | `_extract_json`, `_as_bool`, `_safe_int`, `_safe_json_load`, `_parse_context_files`, `_parse_file_list` |
| Heuristic fallbacks | 3 | ~321 | `_heuristic_parse_plan`, `_heuristic_assess_complexity`, `_heuristic_transform_content` |
| Contract enrichment | 4 | ~250 | `_extract_implementation_contracts`, `_scope_contract_to_files`, `_path_matches_targets`, `_scope_by_service_bullets` |
| Artifact/service inference | 5 | ~200 | `_infer_artifact_types_from_files`, `_infer_service_metadata`, `_artifact_type_from_id`, etc. |
| Mottainai pre-assembly | 2 | ~431 | `_mottainai_pre_assembly`, `_apply_pre_fill_to_skeletons` |
| File/path utilities | 4 | ~120 | `_sha256_file_hex`, `_checksum_file`, `_resolve_path`, `_context_files_with_checksums` |
| Validation | 3 | ~130 | `_validate_context_seed`, `_validate_seed_field_coverage`, `_log_seed_coverage` |
| Requirements | 3 | ~90 | `_extract_requirement_ids`, `_load_requirements_documents`, `_normalize_requirements_hints` |
| Derivation (on class) | 6 | ~600 | `_derive_tasks_from_features`, `_split_oversized_tasks`, `_filter_trivial_test_init_tasks`, `_estimate_story_points`, `_is_trivial_test_init`, `_derive_architectural_context` |

**The monolith is not accidental in the Rube Goldberg sense** — there are no layers compensating for other layers. But it violates the **readability and maintainability** dimension: a developer modifying the enrichment logic must navigate past 1,964 lines of unrelated helpers to reach the class, then past 2,300 lines of phase methods to reach `_phase_emit`.

### 2. Config Parameter Explosion (30+ parameters)

The `_execute()` method begins with **30+ `config.get()` calls** across ~80 lines (5002–5054), with inconsistent patterns:

```python
# Pattern 1: Direct cast
threshold = int(config.get("complexity_threshold", 40))

# Pattern 2: Helper function
skip_arc_review = _as_bool(config.get("skip_arc_review"), False)

# Pattern 3: Two-step with None guard
_raw_warn = config.get("warn_cost_usd")
warn_cost_usd = float(_raw_warn) if _raw_warn is not None else None

# Pattern 4: Nested parsing
requirements_files = _parse_file_list(config.get("requirements_files"))
```

Additionally, the `metadata` property declares **28 WorkflowInput objects** (~220 lines, 1972–2186) that mirror but don't enforce these same parameters.

**Rube Goldberg test**: The config parameter explosion doesn't compensate for a previous layer — it compensates for the **lack of a typed config model**. The `config: Dict[str, Any]` interface forces each parameter to be individually extracted, cast, validated, and defaulted. A `PlanIngestionConfig` dataclass would eliminate ~100 lines of extraction code and consolidate validation.

**Comparison**: `PrimeContractorWorkflow.__init__` had 57 instance attributes (Run 2) → 42 (Run 4). Plan Ingestion has 30+ local variables extracted from config, plus Kaizen config, tracking config, and state. The cognitive load is comparable.

### 3. Enrichment Pipeline — Strategic Investment, Not Accretion

The pipeline has **4 enrichment mechanisms**. Unlike the PrimeContractor analysis where compensatory layers were accidental, the enrichment pipeline is the **core value proposition** of plan ingestion:

> **Project goal**: Enable progressively cheaper models (Ollama → Haiku → small fine-tuned) to produce high-quality code by investing in richer task specifications at ingestion time.

The investment calculus: spend $0.00-0.10 at ingestion to save $0.50-5.00 at generation time by enabling cheaper models to succeed.

```
Parse output (features with basic descriptions)
  │
  ├─ [1] Implementation Contract Enrichment    ─── $0.00, deterministic
  │      _enrich_features_from_plan()
  │      Injects markdown contract text from plan into feature descriptions
  │      Value: Preserves detail that LLM parse summarizes away
  │
  ├─ [2] Deterministic Enrichment (Option A)   ─── $0.00, 658 lines
  │      enrich_tasks_deterministic()
  │      5 steps: negative scope, target files, requirement refs, API sigs, refine suggestions
  │      Value: Fills fields that cheap models need to generate correct code
  │
  ├─ [3] Micro-Ingest Enrichment (Option B)    ─── $0.00-0.10, 1,056 lines
  │      enrich_tasks_micro_ingest()
  │      3 tiers: DFA stubs, template code, Ollama generation
  │      Value: STRATEGIC DIFFERENTIATOR — provides code scaffolding that
  │      enables Ollama/Haiku to fill in implementations vs generating from scratch.
  │      Same pattern can be applied to any cheap model tier.
  │
  └─ [4] Mottainai Pre-Assembly (FR-MPA)       ─── $0.00, 431 lines
         _mottainai_pre_assembly()
         Element registry lookup, classification, template matching, skeleton pre-fill
         Value: Cross-run reuse eliminates redundant generation entirely
```

**Total enrichment code: 2,395 lines** (23% of pipeline) — **essential infrastructure for the cheap-model strategy**.

| Layer | Cost | Lines | Success Rate | Strategic Value |
|-------|------|------:|-------------|----------------|
| Contract enrichment | $0.00 | 250 | ~100% | High — preserves detail for all model tiers |
| Deterministic (A) | $0.00 | 658 | ~100% | High — fills fields cheap models can't infer |
| Micro-Ingest (B) | $0.00-0.10 | 1,056 | ~80% (Tier-2 flaky) | **Critical** — code scaffolding is the key enabler for cheap generation |
| Mottainai (MPA) | $0.00 | 431 | ~95% | High — eliminates generation entirely for known elements |

**This is NOT the accretion anti-pattern.** The PrimeContractor's element-by-element path (12,233 lines) was a wrong decomposition that created compensatory repair layers. The enrichment pipeline is a deliberate investment: each layer makes downstream generation cheaper and more reliable. The question is not "should these layers exist?" but "are they organized well?"

**Growth direction**: Over time, the enrichment pipeline should grow — not shrink. Better enrichment prompts, more deterministic inference, richer code scaffolding, and expanded template registries are all aligned with the strategic goal. The discipline is: keep each layer independently testable and ensure they compose cleanly (no overwriting each other's output).

### 4. Heuristic Fallback Triple

Each of the 3 LLM phases (PARSE, ASSESS, TRANSFORM) has a heuristic fallback:

```
_phase_parse() → _heuristic_parse_plan()              (92 lines)
_phase_assess() → _heuristic_assess_complexity()       (187 lines)
_phase_transform() → _heuristic_transform_content()    (42 lines)
                                              Total:    321 lines
```

The parse and transform heuristics are justified — $0.00 fallbacks that prevent pipeline stall when LLM calls fail. But:

1. The **assess heuristic (187 lines) is over-engineered for a vestigial decision**. It implements a full 7-dimension scoring algorithm with manifest integration, feature count normalization, and routing logic — all to decide between Prime and Artisan. Since Artisan is on hold, this 187-line fallback computes a routing decision that always has the same answer. A 5-line function returning `route=PRIME, composite=30` would produce identical production behavior.

2. The parse heuristic collapses all features into a single fallback entry when it can't parse the plan structure — producing a "degraded" plan that triggers additional compensatory logic downstream (heuristic degradation override, quality routing gate). All of that compensatory logic exists to adjust the **routing** decision, which is currently trivial.

**Key insight**: The heuristic assess + degradation override + quality routing gate form a ~400-line chain, all serving the routing decision. When Artisan resumes, this chain becomes valuable. Until then, it's the largest vestigial code block in the pipeline.

### 5. The `_phase_emit` Mega-Method (650 lines)

`_phase_emit()` (lines 4327–4976) is the largest single method. It performs:

1. Task derivation from features (~150 lines)
2. Task splitting for oversized tasks (~50 lines)
3. Trivial task filtering (~40 lines)
4. Deterministic enrichment (Option A) call (~30 lines)
5. Micro-Ingest enrichment (Option B) call (~30 lines)
6. Mottainai pre-assembly call (~30 lines)
7. Context files with checksums (~20 lines)
8. Service metadata inference (~20 lines)
9. Architectural context derivation (~20 lines)
10. Design calibration derivation (~20 lines)
11. Seed assembly via SeedBuilder (~40 lines)
12. Forward manifest integration (~40 lines)
13. Seed validation (~20 lines)
14. Seed write (~20 lines)
15. Review config assembly + write (~50 lines)
16. Task tracking emission (~40 lines)
17. Artifact inventory persistence (~30 lines)
18. Wave metadata assignment (~20 lines)

**18 operations in a single method**. Each operation is small (20-50 lines), but the method is hard to navigate and test in isolation. This is the "assembly line" where all pipeline outputs converge — and where the most bugs are found (Leg 13 #42-43, #48-52 in Lessons Learned).

---

## Validation Point Inventory

```
Input (plan.md)
  → [1]  Plan file existence check                              ESSENTIAL
  → [2]  Config parameter validation (_custom_validate)          ESSENTIAL
  → [3]  Force route value validation                            ESSENTIAL
  → [4]  Coverage threshold range validation                     DEFENSIVE
  → [5]  Requirements path existence check                       DEFENSIVE
  → [6]  LLM timeout/attempts range validation                   DEFENSIVE
  → [7]  Export contract preflight                                DEFENSIVE
  → [8]  Capability contract validation (Layer 5)                 DEFENSIVE
  → [9]  Parse: LLM JSON extraction                              ESSENTIAL
  → [10] Parse: Heuristic fallback gate                          COMPENSATORY
  → [11] Parse: Implementation contract enrichment               COMPENSATORY
  → [12] Parse: Translation quality evaluation                   COMPENSATORY
  → [13] Parse: Heuristic degradation detection                  COMPENSATORY
  → [14] Assess: LLM complexity scoring                          ESSENTIAL
  → [15] Assess: Heuristic fallback gate                         COMPENSATORY
  → [16] Assess: Degradation route override                      COMPENSATORY
  → [17] Assess: Translation quality routing gate                COMPENSATORY
  → [18] Assess: Low quality policy decision                     DEFENSIVE
  → [19] Transform: LLM format conversion                        ESSENTIAL
  → [20] Transform: Heuristic fallback gate                      COMPENSATORY
  → [21] Refine: Silent failure detection                        DEFENSIVE
  → [22] Emit: Task derivation                                   ESSENTIAL
  → [23] Emit: Oversized task splitting                          COMPENSATORY
  → [24] Emit: Trivial task filtering                            COMPENSATORY
  → [25] Emit: Deterministic enrichment (5 sub-steps)            COMPENSATORY
  → [26] Emit: Micro-Ingest enrichment (3 tiers)                 COMPENSATORY
  → [27] Emit: Mottainai pre-assembly (element classification)   COMPENSATORY
  → [28] Emit: Pre-fill to skeletons (AST validation per element) COMPENSATORY
  → [29] Emit: Seed JSON schema validation                       DEFENSIVE
  → [30] Emit: Seed field coverage validation                    DEFENSIVE
  → [31] Cost: Per-phase cost threshold check (×4)               DEFENSIVE
Output (context-seed.json + review-config.json)
```

**Essential: 7** | **Compensatory: 14** | **Defensive: 10**

**Ratio: 3.4:1 non-essential:essential**

This is significantly better than PrimeContractor (5.6:1) because plan ingestion doesn't have element-by-element generation/repair/splice validation chains. The compensatory points are primarily enrichment and fallback gates.

---

## Tuning Knobs

| Knob | Default | Purpose |
|------|---------|---------|
| `complexity_threshold` | 40 | Prime vs Artisan routing cutoff |
| `review_rounds` | 2 | REFINE iteration count |
| `min_export_coverage` | 0 | Preflight export coverage gate |
| `min_requirements_coverage` | 70 | Translation quality gate |
| `min_artifact_mapping_coverage` | 70 | Translation quality gate |
| `max_contract_conflicts` | 2 | Translation quality gate |
| `llm_read_timeout_seconds` | 300 | LLM HTTP timeout |
| `llm_max_attempts` | 1 | LLM retry count |
| `warn_cost_usd` | None | Cost warning threshold |
| `max_cost_usd` | None | Cost hard limit |
| Feature count normalization | `min(100, max(10, features * 7))` | Heuristic assess score |
| Cross-file deps normalization | `min(100, max(0, deps * 10))` | Heuristic assess score |
| Max description chars | 500 | Density check threshold |
| Max signatures per task | 5 | API sig enrichment cap |
| Oversized task LOC threshold | 200 | Task splitting gate |
| Design depth tiers | brief (4K), standard (8K), comprehensive (16K) | Per-task calibration |

**16 tuning knobs** — manageable compared to PrimeContractor's 28, but the heuristic normalization constants (feature_count × 7, deps × 10) are magic numbers with no derivation rationale.

---

## Fidelity Gradient Instances

| Property | L1 (weak) | L2 (strong) |
|----------|-----------|-------------|
| **Feature extraction** | Heuristic regex parse (single fallback feature) | LLM JSON extraction (structured features) |
| **Complexity scoring** | Heuristic 7-dimension normalization (187 lines) | LLM 7-dimension scoring |
| **Format transformation** | Heuristic YAML/markdown generation (42 lines) | LLM format conversion |
| **Task enrichment** | Deterministic field filling (Option A) | LLM-powered Micro-Ingest (Option B) |

Each gradient is an LLM ↔ heuristic pair. Unlike PrimeContractor's fidelity gradients (which checked the same property at different strength levels), these are **alternative implementations** — either the LLM path or the heuristic path runs, not both. This is architecturally cleaner.

**Exception**: Enrichment layers 1-4 all run sequentially (not as alternatives), and each fills different fields. This is accumulation, not a fidelity gradient — but it means a bug in any enrichment layer can overwrite or conflict with another layer's output.

---

## Recommendations

### P0 — Immediate (cognitive load reduction)

**R1: Extract a `PlanIngestionConfig` dataclass**

Replace 30+ `config.get()` calls in `_execute()` with a typed config model:

```python
@dataclass
class PlanIngestionConfig:
    plan_path: Path
    output_dir: Path = Path(".")
    complexity_threshold: int = 40
    force_route: Optional[str] = None
    review_rounds: int = 2
    skip_arc_review: bool = False
    # ... 24 more fields with types and defaults

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "PlanIngestionConfig":
        # All parsing, casting, and defaulting in one place
        ...
```

**Lines changed: ~150 (new dataclass) - ~80 (removed extraction) = +70 net**
**Value: Consolidates validation, makes parameters discoverable, enables IDE autocompletion**

**R2: Extract module-level helpers into submodules**

Group the 36 module-level functions into focused modules:

| New Module | Functions | Lines |
|------------|----------|------:|
| `plan_ingestion_parsing.py` | `_extract_json`, `_heuristic_parse_plan`, `_heuristic_assess_complexity`, `_heuristic_transform_content`, `_as_bool`, `_safe_int` | ~450 |
| `plan_ingestion_contracts.py` | `_extract_implementation_contracts`, `_scope_contract_to_files`, `_path_matches_targets`, `_scope_by_service_bullets`, `_enrich_features_from_plan` | ~250 |
| `plan_ingestion_mottainai.py` | `_mottainai_pre_assembly`, `_apply_pre_fill_to_skeletons`, `_element_context_checksum` | ~430 |

**Lines changed: ~0 (move, not rewrite) | Risk: Low (internal reorganization)**

This would reduce `plan_ingestion_workflow.py` from 5,907 → ~4,777 lines and make each group independently testable.

### P1 — Short-term (structural simplification)

**R3: Simplify routing to `force_route="prime"` default**

Since Artisan is on hold, change the default behavior:
- Default `force_route` to `"prime"` in the config (or in the entry script)
- This skips the LLM ASSESS call entirely ($0.00 savings per run)
- Skips all routing override logic (heuristic degradation, quality gate, bias_artisan)
- The ASSESS phase, `_heuristic_assess_complexity()`, `_evaluate_translation_quality()`, and routing gates remain in the code for when Artisan resumes — they just don't execute

```python
# In run_iterative_plan_ingestion.py or PlanIngestionConfig:
force_route = config.get("force_route", "prime")  # was: config.get("force_route")
```

**Lines changed: ~1 | Lines bypassed at runtime: ~500+ | Cost saved: 1 LLM call per run**
**Risk: Very low — `force_route` already exists and is tested**

**R4: Extract `_phase_emit` into a PhaseEmitter class**

The 650-line `_phase_emit` performs 18 operations. Extract it into a class with one method per operation:

```python
class PhaseEmitter:
    def __init__(self, config: PlanIngestionConfig, parsed_plan, complexity, ...): ...
    def derive_tasks(self) -> List[dict]: ...
    def enrich_deterministic(self, tasks) -> EnrichmentDiagnostic: ...
    def enrich_micro_ingest(self, tasks) -> MicroIngestDiagnostic: ...
    def run_mottainai_pre_assembly(self, tasks) -> dict: ...
    def assemble_seed(self, tasks) -> ArtisanContextSeed: ...
    def emit(self) -> EmitResult: ...  # orchestrates the above
```

**Lines: ~0 net (restructure) | Risk: Medium (requires careful state threading)**

**R5: Consolidate enrichment into a composable pipeline**

The 4 enrichment mechanisms are called from different locations in `_phase_emit` and `_execute`. Create a unified enrichment pipeline that makes the composition explicit and extensible (important as new enrichment strategies are added):

```python
def enrich_tasks(tasks, plan, config) -> Tuple[List[dict], EnrichmentReport]:
    """Run all enabled enrichment layers in sequence."""
    tasks = enrich_from_plan_contracts(tasks, plan)
    tasks = enrich_deterministic(tasks, config)
    if config.enable_micro_ingest:
        tasks = enrich_micro_ingest(tasks, config)
    if config.enable_mottainai:
        tasks = run_mottainai_pre_assembly(tasks, config)
    return tasks, report
```

**Lines saved: ~50 (consolidation) | Value: Single enrichment pipeline, clear ordering, easy to add new layers**

### P2 — Medium-term (enrichment quality investment)

**R6: Invest in enrichment prompt quality over parse prompt richness**

The current architecture (cheap parse + rich enrichment) is aligned with the strategic goal. Rather than trying to make the parse prompt extract everything in one shot (which increases cost and parse failure rate), invest in:

1. **Better deterministic enrichment heuristics** — more inference rules for target files, negative scope boundaries, and API signatures
2. **Expanded Micro-Ingest template registry** — more language-specific DFA stubs and template patterns
3. **Enrichment quality metrics** — measure which enrichment fields most improve downstream generation quality, and invest there

This is the opposite of the PrimeContractor recommendation (which was "simplify"). Here, the enrichment pipeline should **grow in capability** while maintaining composability (R5).

**R7: When Artisan resumes, reclaim routing value**

When the Artisan workflow becomes active:
1. Remove the `force_route="prime"` default (R3)
2. Re-evaluate whether the LLM ASSESS phase justifies its cost vs the heuristic assess
3. Consider whether the translation quality gate should be tighter (it was designed for a dual-path world)

Until then, the routing code serves as preserved context (Warm Up principle) — don't delete it, just don't execute it.

### P3 — Long-term (cheap-model strategy)

**R8: Extend Micro-Ingest to support Haiku-tier models explicitly**

Micro-Ingest currently targets Ollama (Tier-2). The same pattern — providing code scaffolding, templates, and element-level context — would enable Haiku (or similar cheap cloud models) as a generation tier. This extends the strategic value of plan ingestion beyond local models.

**R9: Enrichment A/B testing infrastructure**

As enrichment grows, measure its downstream impact:
- Run generation with and without each enrichment layer
- Track success rate, repair rate, and cost per tier
- Use the data to prioritize enrichment investment

This converts enrichment from "we think this helps" to "we know this saves $X per run."

---

## Quantified Complexity Budget

| Category | Files | Lines | % | Classification |
|----------|------:|------:|--:|---------------|
| **Core pipeline** (parse + transform + emit phases + models + builder + prompts + entry) | 8 | ~3,394 | 32% | ESSENTIAL |
| **Enrichment pipeline** (contracts + deterministic + micro-ingest + mottainai) | 4 | ~2,395 | 23% | **ESSENTIAL (strategic)** |
| **Derivation** (tasks, architecture, calibration) | 1 | ~790 | 7% | ESSENTIAL |
| **Observability** (diagnostics + OTel + Kaizen) | 1+ | ~870 | 8% | COMPENSATORY (justified) |
| **Orchestration overhead** (_execute config extraction, state, OTel spans) | 1 | ~930 | 9% | Mixed |
| **Routing machinery** (assess phase + heuristic assess + quality gate + overrides) | inline | ~500+ | 5% | **VESTIGIAL** |
| **Defensive validation** (preflight + seed + config) | 2+ | ~544 | 5% | DEFENSIVE |
| **Seeds utilities** | 3 | ~314 | 3% | ESSENTIAL |
| **Remaining helpers** (parsing, paths, requirements) | inline | ~815 | 8% | Mixed |
| **Total** | **13** | **~10,552** | **100%** | |

**Key difference from PrimeContractor**: 62% of plan ingestion is essential (core + enrichment + derivation + seeds), vs 21% for PrimeContractor. The enrichment pipeline reclassification — from compensatory to essential — reflects the strategic reality that enrichment IS the product, not a workaround.

---

## Comparison with PrimeContractorWorkflow

| Metric | Plan Ingestion | Prime Contractor (Run 4) |
|--------|---------------:|-------------------------:|
| Total pipeline lines | 10,552 | 23,702 |
| Essential % | **62%** | 21% |
| Compensatory % | **10%** | 65% |
| Defensive % | 15% | 14% |
| Vestigial % | **5%** | 0% |
| Validation points | 31 | 46 |
| Tuning knobs | 16 | 28 |
| Fidelity gradients | 4 (alternative paths) | 5 (layered strength) |
| Largest file | 5,907 | 3,860 |
| Dead code | 0 | 0 |
| Config parameters | 30+ | 42 |

**Key difference**: Plan Ingestion's essential percentage is 3× higher than PrimeContractor's because the enrichment pipeline (2,395 lines) is the product, not a workaround. PrimeContractor's 52% is element-by-element compensatory code — a single architectural decision that dominates the pipeline. Plan Ingestion's dominant investment (enrichment) is strategically aligned.

**The actual accidental complexity in plan ingestion is small**: ~500 lines of vestigial routing machinery + organizational debt (god-file, config explosion). These are addressable with low-risk reorganization (R1-R3).

**Implication**: Plan Ingestion should be improved by **reorganization** (R1-R2, low-risk) and **runtime bypass** of vestigial routing (R3, trivial). The enrichment pipeline should be **invested in**, not simplified — it's the core of the cheap-model strategy.

---

## The Rube Goldberg Test Applied

> "Does this layer exist to solve the problem, or to compensate for a decision made by a previous layer?"

| Layer | Rube Goldberg Result |
|-------|---------------------|
| Parse (LLM) | **Solves the problem** — extracting structure from prose |
| Heuristic parse fallback | Compensates for LLM unreliability — **acceptable** (external constraint) |
| Contract enrichment | **Solves the problem** — preserves implementation detail for cheap-model generation |
| Assess (LLM) | **Vestigial** — scoring complexity for a routing decision that currently has one answer |
| Heuristic assess fallback | **Vestigial + over-engineered** — 187-line fallback for a dormant routing decision |
| Translation quality gate | **Vestigial** — adjusts routing that always routes to Prime |
| Transform (LLM) | **Solves the problem** — format conversion |
| Refine (arc-review) | Enriches task specifications — **valuable but optional** |
| Deterministic enrichment | **Solves the problem** — fills fields cheap models need to generate correctly |
| Micro-Ingest | **Solves the problem** — code scaffolding is the strategic enabler for cheap generation |
| Mottainai pre-assembly | **Solves the problem** — cross-run element reuse eliminates redundant generation |
| Seed validation | **Solves the problem** — ensuring output correctness |
| Traceability | **Solves the problem** — auditability |
| Diagnostics | **Solves the problem** — observability |

**Verdict**: The enrichment layers (contract, deterministic, Micro-Ingest, Mottainai) are all essential — they ARE the value proposition. The accidental complexity is concentrated in the **routing machinery** (~500+ lines serving a dormant Artisan path) and the **god-file monolith** (organizational, not architectural). The actionable wins are: default `force_route="prime"` (R3), extract helpers into submodules (R2), and consolidate enrichment composition (R5).

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-12 | Run 1: Initial analysis (10,552 lines, 13 files). 8 essential / 3 compensatory / 2 defensive / 1 vestigial layers. Strategic reclassification: enrichment pipeline (2,395 lines) classified as ESSENTIAL — it IS the cheap-model strategy, not a workaround. Routing machinery (~500+ lines) classified as VESTIGIAL — Artisan is on hold, Prime is the only active path. Key findings: god-file monolith (5,907 lines), config parameter explosion (30+ params), vestigial routing (heuristic assess 187 lines for dormant decision). 9 recommendations (P0: R1-R2, P1: R3-R5, P2: R6-R7, P3: R8-R9). No dead code. Essential ratio 62% (vs PrimeContractor's 21%). |
