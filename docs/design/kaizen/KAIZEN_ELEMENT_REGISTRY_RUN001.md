# Kaizen Analysis: Element Registry Run 001

**Date:** 2026-03-08
**Run ID:** `run-001-20260307T1917`
**Project:** `element-registry`
**Plan source:** `docs/design/element-registry/IMPLEMENTATION_PLAN.md`
**Route:** Prime (complexity score 58, seed quality 0.967)

---

## 1. Run Overview

| Metric | Value |
|--------|-------|
| Total tasks | 32 (3 phases) |
| Completed | 7 (PI-001 through PI-007) |
| Failed | 1 (PI-008) |
| Pending | 24 (PI-009 through PI-032) |
| Progress | 21.9% |

### Cost Breakdown

| Round | Features | Cost | Outcome |
|-------|----------|------|---------|
| Round 1 | PI-002 | $0.38 | PASS (1/1) |
| Round 2 | PI-001, PI-003, PI-004, PI-005, PI-006 | — (manual) | PASS (done outside pipeline) |
| Round 3 | PI-007, PI-008 | $1.60 | PARTIAL (1/2) |
| **Total** | 8 attempted | **$1.98** | 7 done, 1 failed |

### Plan Ingestion Metrics

| Phase | Cost | Tokens (in/out) | Time |
|-------|------|-----------------|------|
| parse | $0.16 | 10,306 / 8,570 | 103s |
| assess | $0.01 | 1,247 / 364 | 8s |
| transform | $0.25 | 3,662 / 16,142 | 247s |
| **Total ingestion** | **$0.42** | 15,215 / 25,076 | 359s |

---

## 2. Feature Results

### PI-007: ForwardManifest element index tests — PASS ($0.66)

**Target:** `tests/unit/test_forward_manifest.py`
**Generated file:** 36.9 KB

#### Micro-Prime Performance

| Metric | Value |
|--------|-------|
| Elements identified | 87 (78 Ollama + 9 cloud) |
| Decomposed (moderate → simple) | 21 |
| Decomposition failures | 0 |
| Micro-prime cost | $0.00 (local Ollama) |
| Cloud fallback cost | $0.66 |

#### Repair Pipeline Activity

Common repair steps applied across 78 Ollama-generated elements:

| Repair Step | Occurrences | Effect |
|-------------|-------------|--------|
| `bare_statement_wrap` | ~30+ | Wrapped bare method bodies into `def` stubs |
| `import_completion` | ~20+ | Added missing imports from manifest |

#### Issue: Cloud Fallback Discards Ollama Work

The pipeline generated 78 elements locally (Ollama), then delegated to cloud fallback which rewrote the **entire file** for $0.66. Evidence:

- `fallback_files_delegated: 2`, `fallback_files_written: 2` — same file delegated twice
- History shows duplicate entry for `tests/unit/test_forward_manifest.py` in the `files` array
- All 78 Ollama-generated elements were effectively discarded

**Root cause:** Assembly defect detection likely triggered on the micro-prime-assembled file (skeleton markers, stubs, or nested duplicate functions), causing cloud fallback to regenerate from scratch.

**Mottainai violation:** The 78 local elements represent ~4 minutes of Ollama inference time, discarded because the pipeline has no mechanism to forward successful element-level generations to cloud fallback as context. This is exactly the gap that the Element Registry (REQ-MP-1102, REQ-MP-1103) is designed to close.

---

### PI-008: Plan ingestion registry population — FAIL ($0.94)

**Target:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`
**Error:** `"No files were integrated"`

#### Element Decomposition Results

| Tier | Count | Succeeded | Failed | Rate |
|------|-------|-----------|--------|------|
| trivial | 1 | 1 | 0 | 100% |
| simple | 15 | 15 | 0 | 100% |
| moderate | 63 | 16 | 47 | 25% |
| complex | 0 | 0 | 0 | — |
| **Total** | **79** | **32** | **47** | **40%** |

All 47 moderate failures had escalation reason `not_decomposable`. These are domain-specific workflow functions that don't decompose cleanly into SIMPLE sub-elements:

| Failed Element | Tier | Reason |
|----------------|------|--------|
| `_execute` | moderate | Core workflow orchestration — too complex for decomposition |
| `_derive_architectural_context` | moderate | Domain-specific LLM prompt construction |
| `_evaluate_translation_quality` | moderate | Quality evaluation with multiple heuristics |
| `_custom_validate` | moderate | Validation logic with format-specific branches |
| `_derive_design_calibration` | moderate | Calibration hint extraction |
| `_checksum_file` | moderate | File I/O + hashing |
| `_context_files_with_checksums` | moderate | Path resolution + checksum aggregation |
| `_ensure_onboarding_in_context_files` | moderate | Onboarding file injection |
| `_estimate_story_points` | moderate | Heuristic estimation |
| `_artifact_target_from_id` | moderate | ID → file path mapping |
| `_artifact_type_from_id` | moderate | ID → type classification |
| `_as_bool` | moderate | Type coercion utility |
| *(+35 more)* | moderate | Various workflow helpers |

#### Why Integration Failed — Full Chain Trace

The failure was a **size regression block** in the integration engine. Here is the complete causal chain, traced from seed through generation to rejection.

##### Step 1: Pipeline correctly identified edit mode

The enrichment detected that the target file exists (`has_existing_files: true`). The spec prompt used the `draft_edit` template and explicitly instructed:

```
## EDIT MODE — Existing Code Modification
**Task type: Update** existing code.
Your specification must:
- Describe ONLY the additions and modifications needed
- List which existing functions/classes to keep unchanged
- NOT redesign or restructure existing code
```

The pipeline **did** recognize this as an edit task. The failure is downstream.

##### Step 2: Context budget truncated the existing file from 4,773 to 1,116 lines

The `EXISTING_FILES_BUDGET_BYTES` constant in `implementation_engine/budget.py` caps existing file context at **40 KB**. The actual `plan_ingestion_workflow.py` is ~167 KB (4,773 lines). The drafter's `build_existing_files_section()` truncated it:

```
### `src/startd8/workflows/builtin/plan_ingestion_workflow.py` (1116 lines)
```

The LLM saw only 23% of the file — the first 1,116 lines (imports through `_validate_seed_field_coverage`). The remaining 3,657 lines (76%) — including the core `PlanIngestionWorkflow` class, `_execute`, all phase methods — were invisible.

##### Step 3: Output format told the LLM the file had 1,116 lines

The `build_output_format()` function computes `total_lines` from the **truncated** content passed via `existing_files`, not from the actual file on disk. This produced:

```
You are EDITING an existing file (1116 lines).
CRITICAL SIZE CONSTRAINT: Your output must be AT LEAST 0 lines.
```

`min_output_lines=0` and `min_pct=0` — the output format imposed **no minimum size guard**. The LLM was free to produce a file of any length.

##### Step 4: Cloud fallback regenerated the file as 1,542 lines

With only 1,116 lines visible and a task description saying "populate ElementRegistry," the cloud model generated a 1,542-line file. This is actually **longer** than the visible portion, so the model tried to add content. But it couldn't preserve the 3,657 lines it never saw. The generated file:

- Has correct structure for the visible portion (imports, constants, helper functions)
- Includes the requested `_populate_element_registry()` function (line 841)
- Has a `PlanIngestionWorkflow` class with `__init__` accepting `element_registry`
- **Hallucinated imports** because the truncated context excluded the real import block:

```python
# Generated (hallucinated)                    # Actual (existing)
from startd8.workflow_base import ...         # startd8.workflows.base
from startd8.workflow_types import ...        # No such module (models in plan_ingestion_models.py)
from startd8.utils.kaizen_utils import ...    # No such module (in plan_ingestion_diagnostics.py)
from startd8.utils.seed_utils import ...      # No such module (functions are inline in the file)
from startd8.utils.io_utils import ...        # No such module (in startd8.utils.file_operations)
from startd8.utils.token_utils import ...     # startd8.utils.token_usage
```

##### Step 5: Integration engine rejected — size regression

The integration engine compared:

| Metric | Value |
|--------|-------|
| Source (generated) | 1,542 lines |
| Target (actual on disk) | 4,773 lines |
| Ratio | 0.323 (32.3%) |
| Threshold | 0.60 (60%) |
| Min lines for check | 50 |

`0.323 < 0.60` and `4,773 > 50` → **size regression blocked**.

The merge-repair fallback (`_merge_subset_into_target`) was either not enabled or could not merge the 1,542-line generated file into the 4,773-line target. Result: `"No files were integrated"`.

##### Root Cause Summary

```
4,773-line file
  → 40 KB budget truncates to 1,116 lines (23%)
    → LLM sees 1,116 lines, generates 1,542 lines
      → Integration compares 1,542 vs 4,773 = 32.3%
        → Size regression threshold 60% BLOCKS integration
          → "No files were integrated"
```

**The pipeline correctly identified edit mode but the context budget made it impossible for the LLM to preserve a file it couldn't see.** The 40 KB budget is designed for typical source files (200-400 lines). For a 4,773-line file, the budget would need to be ~167 KB — 4x the current limit.

##### Structural Gaps Identified

1. **`min_output_lines` hardcoded to 0**: The output format template computes `existing_line_count` from the truncated content (1,116), not the actual file (4,773). Even if `min_pct` were set to 80%, it would require 893 lines — well under the 4,773-line original. The minimum should be computed from the **actual file on disk**, not the truncated context.

2. **No "file too large for edit" circuit breaker**: When a file exceeds the context budget, the pipeline should detect this and either (a) switch to a search-and-replace editing strategy instead of complete-file output, or (b) fail-fast with a clear error rather than generating an incomplete file that will be blocked downstream.

3. **Context budget is file-count-unaware**: The 40 KB budget is per-task, not per-file. A single-file edit task targeting a 167 KB file gets the same budget as a task targeting a 5 KB file. For single-file edits, the budget should scale to accommodate the target.

4. **Hallucinated imports are a symptom, not the cause**: The cloud model hallucinated imports because the truncated context excluded the actual import block (which was within the 1,116 visible lines — lines 1-93). In this case, the real imports WERE visible. The hallucination happened because the cloud model regenerated the file from scratch rather than modifying the visible code. This suggests the cloud fallback path may not preserve the micro-prime skeleton/existing-file content.

---

## 3. Cross-Feature Patterns

### Pattern: `repeated_escalation` (Medium Severity)

**Detection:** Kaizen system identified `not_decomposable` escalation across both PI-007 and PI-008.

**Missing template:** The log shows `No suggestion template for pattern type 'repeated_escalation' — skipping.` — this pattern type has no kaizen suggestion template, so no automated recommendation was generated.

**Impact:** The decomposer's `not_decomposable` path is the primary bottleneck for moderate-tier elements in real-world files. Of 67 moderate elements across both features, many could not be decomposed into simple sub-elements.

### Tier Distribution (158 elements across 2 features)

| Tier | Count | % |
|------|-------|---|
| trivial | 1 | 0.6% |
| simple | 81 | 51.3% |
| moderate | 67 | 42.4% |
| complex | 9 | 5.7% |

The moderate tier is the largest source of failures. The simple tier has a near-100% success rate, confirming that the micro-prime engine works well within its design envelope.

---

## 4. Routing Anomaly

The assess phase scored complexity at 58 with route decision "prime", but the reasoning text explicitly states: *"The composite score of 58 routes this to artisan."* This contradicts the actual route taken.

| Signal | Value |
|--------|-------|
| Composite score | 58 |
| Dimension spread | 45 |
| Route decision | prime |
| Route margin | 18 |
| Reasoning conclusion | "routes this to artisan" |

With 32 interdependent tasks spanning 3 phases, touching 8 pipeline phases and multiple integration points, the artisan route may have been more appropriate. The prime route processed tasks individually without the design/review phases that artisan provides.

---

## 5. Identified Issues

### ISS-1: Cloud fallback discards successful Ollama generations

**Severity:** Medium
**Affected:** PI-007 (and any future task where micro-prime assembly triggers cloud fallback)
**Evidence:** 78 Ollama-generated elements discarded when cloud fallback rewrote the file
**Mottainai rules violated:** Rule 1 (inventory before generating), Rule 2 (forward, don't regenerate)
**Fix:** Element Registry integration (REQ-MP-1102, REQ-MP-1103) — persist element generations and pass to cloud as context

### ISS-2: Context budget truncation makes large-file edits impossible

**Severity:** High
**Affected:** PI-008 (and any future task targeting files >40 KB)
**Evidence:** 4,773-line file truncated to 1,116 lines (23%) by 40 KB `EXISTING_FILES_BUDGET_BYTES`; generated 1,542 lines; integration blocked at 32.3% ratio vs 60% threshold
**Root cause chain:** `implementation_engine/budget.py` sets `EXISTING_FILES_BUDGET_BYTES = 40 * 1024`; `drafter.py:build_existing_files_section()` truncates to fit; `build_output_format()` computes `existing_line_count` from truncated content (1,116) not actual file (4,773); `min_output_lines=0` provides no guard; integration engine blocks at `_INTEGRATION_SIZE_REGRESSION_THRESHOLD = 0.60`
**Fix options:**
  - (a) Scale context budget for single-file edit tasks to accommodate the target file
  - (b) Add circuit breaker: when file exceeds budget, switch to search-and-replace editing (diff-based output) instead of complete-file output
  - (c) Compute `min_output_lines` from actual file on disk, not truncated context
  - (d) Short-term: manually implement the ~30-line change for PI-008

### ISS-3: Hallucinated import paths in cloud-generated code

**Severity:** Medium (symptom of ISS-2, not independent)
**Affected:** PI-008
**Evidence:** 6+ non-existent import paths in generated file (`startd8.workflow_base`, `startd8.workflow_types`, etc.)
**Root cause:** Contrary to initial analysis, the real imports WERE visible in the truncated context (lines 1-93 of 1,116). The hallucination happened because the cloud fallback regenerated the file from scratch rather than modifying the visible code. The cloud model appears to have ignored the existing imports section in favor of inventing new ones.
**Fix:** This is secondary to ISS-2. Once the LLM can see the full file (or uses diff-based editing), hallucinated imports should not occur. Additionally, the post-generation `deps_available` validator in the enrichment should catch these before integration.

### ISS-4: Missing kaizen suggestion template for `repeated_escalation`

**Severity:** Low
**Affected:** Kaizen analysis pipeline
**Evidence:** Log: `No suggestion template for pattern type 'repeated_escalation' — skipping.`
**Fix:** Add suggestion template recommending: (a) review decomposer strategy coverage, (b) enrich task descriptions with `api_signatures`, (c) consider cloud-first routing for files with >30% moderate elements

### ISS-5: Routing contradiction (score says prime, reasoning says artisan)

**Severity:** Low
**Affected:** Plan ingestion assess phase
**Evidence:** Composite score 58, route "prime", but reasoning text says "routes this to artisan"
**Fix:** Investigate the assess phase classifier — either the threshold is wrong or the LLM reasoning doesn't match its numeric output. The route_margin of 18 suggests a threshold around 40 (58 - 18 = 40), which may be too low for a 32-task plan.

---

## 6. Recommendations for Next Round

### Immediate (before resuming)

1. **Fix PI-008 manually** — Add `_populate_element_registry()` and the `__init__` constructor change directly to `plan_ingestion_workflow.py`. This is a ~30-line edit, not worth re-running the full generation pipeline.

2. **Mark PI-008 as done** in the task list after manual fix, then resume with PI-009.

### Short-term (for remaining tasks)

3. **Audit remaining edit-mode tasks for context budget fit** — All four remaining edit-mode targets exceed the 40 KB budget:

   | Task | Target File | Lines | Size | Over Budget |
   |------|-------------|-------|------|-------------|
   | PI-010 | `micro_prime/engine.py` | 2,029 | 80 KB | 2x |
   | PI-012 | `micro_prime/prime_adapter.py` | 1,497 | 61 KB | 1.5x |
   | PI-014 | `contractors/prime_contractor.py` | 3,755 | 164 KB | 4x |
   | PI-016 | `scripts/run_prime_workflow.py` | 770 | 30 KB | Under budget |

   Only PI-016 fits within the 40 KB budget. The other three will hit the same ISS-2 truncation/regression chain. Consider implementing ISS-2 fix (b) — diff-based editing for large files — before running PI-010, PI-012, PI-014. Or manually implement these ~30-line edits.

4. **Skip dependency-blocked tasks** — PI-009 depends on PI-008. After fixing PI-008 manually, PI-009 (unit tests for registry population) can be generated.

5. **Parallelize independent tasks** — PI-010 through PI-017 are mostly independent of each other (they share PI-004 as a dependency, which is done). Consider running them in a single batch.

### Medium-term (pipeline improvements)

6. **Add `repeated_escalation` suggestion template** to the kaizen suggestion generator.

7. **Investigate assembly defect detection → cloud fallback** — When cloud fallback is triggered by assembly defects, the successful element generations should be forwarded as context (Element Registry MVP would solve this).

8. **Fix the routing score/reasoning contradiction** in the assess phase classifier.

---

## 7. Task Status After This Round

| Status | Tasks | IDs |
|--------|-------|-----|
| Done | 7 | PI-001, PI-002, PI-003, PI-004, PI-005, PI-006, PI-007 |
| Failed | 1 | PI-008 |
| Pending | 24 | PI-009 through PI-032 |

### Dependency Graph Impact

PI-008's failure blocks:
- **PI-009** (unit tests for registry population) — direct dependency
- No other tasks directly depend on PI-008

All other pending tasks depend on PI-004 (ElementRegistry core, done) or PI-006 (ForwardManifest index, done), so they are unblocked.
