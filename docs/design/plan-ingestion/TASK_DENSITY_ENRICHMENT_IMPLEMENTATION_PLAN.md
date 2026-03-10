# Task Density Enrichment — Option A Implementation Plan

> **Version:** 0.1.0
> **Status:** PLANNED
> **Date:** 2026-03-10
> **Requirements:** [TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md](./TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md) (REQ-TDE-100–106, 300, 303, 400–402)
> **Scope:** Deterministic (zero LLM cost) task enrichment pass between REFINE and EMIT

---

## Summary

Add a deterministic enrichment pass that runs after REFINE and before quality scoring in `_phase_emit()`. The pass extracts signals from existing pipeline artifacts (ParsedFeature fields, plan text, REFINE suggestions) and maps them to per-task seed fields. This closes the density gap identified in run-019 where 0/6 tasks had code examples, requirement refs, or negative scope despite those signals being available in the pipeline.

**Key discovery:** `negative_scope` and `api_signatures` are ALREADY forwarded from ParsedFeature to task context at lines 3157-3162 of `_derive_tasks_from_features()`. REQ-TDE-100 (negative scope) is partially satisfied. The real gap is in requirement reference injection, REFINE suggestion mapping, and target files inference for tasks where PARSE didn't extract explicit paths.

---

## Architecture

### Pipeline Position

```
PARSE → ASSESS → TRANSFORM → REFINE → EMIT
                                         ↑
                                    _phase_emit() {
                                      seed = build_seed(tasks)
                                      seed_dict = seed.to_dict()
                                      ┌─────────────────────────┐
                                      │ enrich_tasks_deterministic() │  ← NEW (line ~4465)
                                      └─────────────────────────┘
                                      task_density = compute_task_density()
                                      seed_quality = compute_seed_quality()
                                      write seed_dict
                                    }
```

### Insertion Point

**File:** `plan_ingestion_workflow.py`, inside `_phase_emit()`, line 4464.

After `seed_dict = seed.to_dict()` (line 4464), before `_task_density = compute_task_density(...)` (line 4467). This ensures enrichment populates fields that the existing quality scoring then captures automatically (REQ-TDE-402).

### Available Data at Insertion Point

| Variable | Source | Used By |
|----------|--------|---------|
| `seed_dict` | `seed.to_dict()` | All enrichment steps (task list) |
| `parsed_plan` | PARSE phase output | REQ-TDE-100 (negative scope), 102 (target files), 103 (API signatures) |
| `review_output` | REFINE phase output | REQ-TDE-104 (REFINE suggestions) |
| `refine_suggestions` | Extracted at line 4335 | REQ-TDE-104 (already computed before seed assembly) |
| `self._plan_text` | Original plan input | REQ-TDE-101 (requirement refs proximity search) |
| `self._kaizen_config` | Kaizen config | REQ-TDE-303 (per-step enable/disable) |

**Note:** `self._plan_text` must be threaded — currently the raw plan text is available as a local in `_execute()` but not stored on `self`. Step 1 addresses this.

---

## Implementation Steps

### Step 0: Thread `plan_text` to `_phase_emit()`

**File:** `plan_ingestion_workflow.py`

The raw plan text is needed for requirement reference proximity search (REQ-TDE-101). Currently available as a local variable in `_execute()` but not passed to `_phase_emit()`.

**Change:** Add `plan_text: str = ""` parameter to `_phase_emit()` signature. Pass `plan_text` from `_execute()` at the call site (line 5338).

**Scope:** 2 lines changed.

### Step 1: Create enrichment module

**File:** `src/startd8/workflows/builtin/plan_ingestion_enrichment.py` (NEW)

Pure functions, no class state, no LLM calls. Each function takes `tasks: List[Dict]` and data sources, modifies tasks in-place, returns a count of enrichments made.

```python
"""Deterministic task enrichment — Option A (REQ-TDE-1xx).

Zero LLM cost. Extracts signals from existing pipeline artifacts
and maps them to per-task seed fields. Runs after REFINE, before
quality scoring in _phase_emit().
"""

import re
from typing import Any, Dict, List, Optional

from ...logging_config import get_logger
from ...utils.prime_task_enrichment import extract_target_files

logger = get_logger(__name__)

_REQ_PATTERN = re.compile(r"\bREQ[-_]?\w+", re.IGNORECASE)


def enrich_negative_scope(
    tasks: List[Dict[str, Any]],
    features: List[Any],
) -> int: ...

def enrich_target_files(
    tasks: List[Dict[str, Any]],
    features: List[Any],
) -> int: ...

def enrich_requirement_refs(
    tasks: List[Dict[str, Any]],
    plan_text: str,
    proximity_chars: int = 500,
) -> int: ...

def enrich_api_signatures(
    tasks: List[Dict[str, Any]],
    features: List[Any],
) -> int: ...

def enrich_refine_suggestions(
    tasks: List[Dict[str, Any]],
    suggestions: List[Dict[str, Any]],
) -> int: ...

def enrich_tasks_deterministic(
    seed_dict: Dict[str, Any],
    *,
    features: Optional[List[Any]] = None,
    plan_text: str = "",
    refine_suggestions: Optional[List[Dict[str, Any]]] = None,
    config: Optional[Any] = None,  # PlanIngestionKaizenConfig
) -> Dict[str, int]: ...
```

The orchestrator `enrich_tasks_deterministic()` calls each step in REQ-TDE-105 order, respects per-step config booleans (REQ-TDE-303), and returns a counters dict for diagnostics (REQ-TDE-400).

**Estimated scope:** ~250 lines.

### Step 2: Implement `enrich_negative_scope()` (REQ-TDE-100)

**Verify existing forwarding:** Lines 3157-3158 already copy `feat.negative_scope` to `ctx["negative_scope"]` during `_derive_tasks_from_features()`. This step only needs to handle tasks where the existing forwarding missed (e.g., if PARSE extracted negative scope at the plan level but not per-feature).

**Logic:**
1. Build `feature_id → feature` lookup from `features` list
2. For each task, get `feature_id` from `task["config"]["context"]["feature_id"]`
3. If `task["config"]["context"].get("negative_scope")` is already non-empty → skip (no-clobber)
4. If matched feature has `negative_scope` → set it
5. Return count of tasks enriched

**Expected impact:** Low incremental (most already forwarded at line 3157). Acts as safety net.

### Step 3: Implement `enrich_target_files()` (REQ-TDE-102)

**3-tier fallback chain:**

1. **Tier 1: Feature target_files** — Copy from linked ParsedFeature if non-empty and task context `target_files` is empty. (Also largely handled at line 3150, but acts as safety net.)
2. **Tier 2: Description regex** — Call `extract_target_files(task_description)` from `utils/prime_task_enrichment.py`.
3. **Tier 3: Convention-based** — Derive from task title using simple heuristics:
   - Title containing "gRPC Server" + service name → `{service_name}/{service_name}_server.py`
   - Title containing "Client" + service name → `{service_name}/{service_name}_client.py`
   - Tag Tier 3 results with `_inferred: true` in context

**No-clobber:** Only set if `target_files` is empty/missing.

### Step 4: Implement `enrich_requirement_refs()` (REQ-TDE-101)

**Logic:**
1. For each task, extract feature name/title
2. Find all occurrences of the feature name in `plan_text`
3. For each occurrence, extract ±`proximity_chars` window
4. Collect all `_REQ_PATTERN` matches from the window
5. Deduplicate against any REQ-* already in the task description
6. If new refs found, append `\n\n## Requirements References\n- REQ-XXX: ...` to `task_description`

**Proximity window:** Default 500 chars (configurable via `enrich_req_proximity_chars` in kaizen config).

**Edge case:** If feature name appears multiple times, union all windows. If feature name is generic (e.g., "API"), skip proximity injection to avoid false positives — only inject if feature name is ≥ 3 words or matches as a phrase.

### Step 5: Implement `enrich_api_signatures()` (REQ-TDE-103)

**Logic:**
1. Build `feature_id → feature` lookup
2. For each task, check if description already contains `` ``` `` blocks → skip if yes (no-clobber)
3. If matched feature has `api_signatures` → format as code-fenced stub:
   ```
   \n\n## API Signatures\n```python\n{signatures}\n```
   ```
4. Limit to 5 signatures per task
5. Return count

**Note:** `api_signatures` is already forwarded to context at line 3161. This step adds them as *description text* (code blocks) so `has_code_examples` density signal flips to `True`.

### Step 6: Implement `enrich_refine_suggestions()` (REQ-TDE-104)

**Logic:**
1. For each accepted suggestion (from `_extract_refine_suggestions_for_seed()` output):
   - If suggestion has `placement` matching a task's `target_files` → map to that task
   - Else if suggestion has `area` → use area→task heuristic mapping:
     - `"interfaces"` → tasks with "API", "gRPC", "service" in title
     - `"data"` → tasks with "model", "schema", "database" in title
     - `"validation"` → tasks with "validation", "input", "check" in title
   - Else → unmapped (shared across all tasks)
2. For mapped suggestions, append `\n\n## Review Guidance (from REFINE)\n- [{area}] {rationale}` to task description
3. For unmapped suggestions, append top 3 (by severity) to all tasks as shared guidance
4. Deduplicate: skip suggestions whose rationale text already appears in description

### Step 7: Implement `enrich_tasks_deterministic()` orchestrator (REQ-TDE-105, 106)

**Logic:**
```python
def enrich_tasks_deterministic(
    seed_dict, *, features=None, plan_text="",
    refine_suggestions=None, config=None,
):
    counters = {}
    cfg = config or PlanIngestionKaizenConfig()  # defaults = all enabled

    if cfg.enrich_negative_scope:
        counters["negative_scope_added"] = enrich_negative_scope(
            seed_dict.get("tasks", []), features or [],
        )
    if cfg.enrich_target_files:
        counters["target_files_inferred"] = enrich_target_files(
            seed_dict.get("tasks", []), features or [],
        )
    if cfg.enrich_requirement_refs:
        counters["requirement_refs_added"] = enrich_requirement_refs(
            seed_dict.get("tasks", []), plan_text,
            proximity_chars=cfg.enrich_req_proximity_chars,
        )
    if cfg.enrich_api_signatures:
        counters["api_signatures_added"] = enrich_api_signatures(
            seed_dict.get("tasks", []), features or [],
        )
    if cfg.enrich_refine_suggestions:
        counters["refine_suggestions_mapped"] = enrich_refine_suggestions(
            seed_dict.get("tasks", []), refine_suggestions or [],
        )

    tasks = seed_dict.get("tasks", [])
    enriched = sum(1 for t in tasks if _was_enriched(t))
    counters["tasks_enriched"] = enriched
    counters["tasks_skipped"] = len(tasks) - enriched

    return counters
```

**Execution order** (REQ-TDE-105): negative scope → target files → requirement refs → API signatures → REFINE suggestions. Each step can build on prior results.

### Step 8: Wire into `_phase_emit()`

**File:** `plan_ingestion_workflow.py`

At line 4464, after `seed_dict = seed.to_dict()`, insert:

```python
# --- Deterministic enrichment (Option A, REQ-TDE-1xx) ---
import time as _time_mod
_enrich_t0 = _time_mod.monotonic()
_enrich_counters = enrich_tasks_deterministic(
    seed_dict,
    features=parsed_plan.features if parsed_plan else None,
    plan_text=plan_text,
    refine_suggestions=refine_suggestions,
    config=self._kaizen_config,
)
_enrich_time_ms = int((_time_mod.monotonic() - _enrich_t0) * 1000)
logger.info(
    "ENRICH-A: %d tasks enriched, %d skipped (%d ms) — %s",
    _enrich_counters.get("tasks_enriched", 0),
    _enrich_counters.get("tasks_skipped", 0),
    _enrich_time_ms,
    {k: v for k, v in _enrich_counters.items() if v > 0},
)
```

This runs before `compute_task_density()` at line 4467, so quality scoring automatically reflects the enrichment (REQ-TDE-402).

### Step 9: Wire `EnrichmentDiagnostic` into diagnostic report (REQ-TDE-400)

**File:** `plan_ingestion_workflow.py` (diagnostic assembly section, lines ~5190-5230)

The `EnrichmentDiagnostic` dataclass already exists in `plan_ingestion_diagnostics.py` (line 72). Populate it from `_enrich_counters` and `_enrich_time_ms`:

```python
enrichment_diag = EnrichmentDiagnostic(
    enabled=True,
    negative_scope_added=_enrich_counters.get("negative_scope_added", 0),
    requirement_refs_added=_enrich_counters.get("requirement_refs_added", 0),
    target_files_inferred=_enrich_counters.get("target_files_inferred", 0),
    api_signatures_added=_enrich_counters.get("api_signatures_added", 0),
    refine_suggestions_mapped=_enrich_counters.get("refine_suggestions_mapped", 0),
    tasks_enriched=_enrich_counters.get("tasks_enriched", 0),
    tasks_skipped=_enrich_counters.get("tasks_skipped", 0),
    time_ms=_enrich_time_ms,
)
```

**Threading:** `_enrich_counters` and `_enrich_time_ms` are local to `_phase_emit()`. Return them as part of `EmitResult` or store on `self._enrichment_counters` for the diagnostic assembly in `_execute()`.

### Step 10: Config already in place (REQ-TDE-300, 303)

**No changes needed.** The `PlanIngestionKaizenConfig` dataclass already has all 6 Option A fields (lines 100-106 of `plan_ingestion_diagnostics.py`):

```python
enrich_negative_scope: bool = True       # REQ-TDE-100
enrich_requirement_refs: bool = True     # REQ-TDE-101
enrich_target_files: bool = True         # REQ-TDE-102
enrich_api_signatures: bool = True       # REQ-TDE-103
enrich_refine_suggestions: bool = True   # REQ-TDE-104
enrich_req_proximity_chars: int = 500    # REQ-TDE-101 proximity window
```

`load_kaizen_config()` already handles unknown keys gracefully. All fields default to enabled.

---

## Implementation Order

| Order | Step | What | REQ | Risk |
|-------|------|------|-----|------|
| 1 | Step 0 | Thread `plan_text` to `_phase_emit()` | — | Low — adds parameter |
| 2 | Step 1 | Create enrichment module skeleton | — | Low — new file |
| 3 | Step 2 | `enrich_negative_scope()` | TDE-100 | Low — safety net over existing forwarding |
| 4 | Step 3 | `enrich_target_files()` | TDE-102 | Medium — Tier 3 heuristics may need tuning |
| 5 | Step 4 | `enrich_requirement_refs()` | TDE-101 | Medium — proximity heuristic may produce false positives |
| 6 | Step 5 | `enrich_api_signatures()` | TDE-103 | Low — straightforward append |
| 7 | Step 6 | `enrich_refine_suggestions()` | TDE-104 | Medium — area→task mapping is heuristic |
| 8 | Step 7 | Orchestrator + no-clobber | TDE-105, 106 | Low — composition of tested parts |
| 9 | Step 8 | Wire into `_phase_emit()` | — | Low — single insertion point |
| 10 | Step 9 | Diagnostic wiring | TDE-400 | Low — dataclass already exists |
| 11 | Tests | Unit + integration | TDE-401, 402 | — |

**Checkpoint after Steps 1-7:** Run enrichment functions in isolation against run-019 task data to validate density signal improvement before wiring into the workflow.

---

## Test Plan

### Unit Tests

**File:** `tests/unit/workflows/test_plan_ingestion_enrichment.py` (NEW)

| Test | Step | What |
|------|------|------|
| `test_negative_scope_forwarded` | 2 | Feature with `negative_scope` → task context has it |
| `test_negative_scope_no_clobber` | 2 | Task with existing negative_scope → not overwritten |
| `test_negative_scope_no_feature_match` | 2 | Task with unknown `feature_id` → no enrichment |
| `test_target_files_tier1_from_feature` | 3 | Feature has `target_files` → copied to empty task |
| `test_target_files_tier2_from_description` | 3 | Description mentions `emailservice/server.py` → extracted |
| `test_target_files_tier3_convention` | 3 | Title "Email Service" → inferred path |
| `test_target_files_no_clobber` | 3 | Task with existing target_files → not overwritten |
| `test_requirement_refs_extracted` | 4 | Plan text with `REQ-PI-003` near feature name → appended |
| `test_requirement_refs_proximity_boundary` | 4 | REQ-* 1000 chars away → not included |
| `test_requirement_refs_no_duplicate` | 4 | REQ already in description → not re-added |
| `test_api_signatures_appended` | 5 | Feature has signatures → code block in description |
| `test_api_signatures_skip_existing_code` | 5 | Description has ``` blocks → no code added |
| `test_api_signatures_limit_5` | 5 | Feature with 8 signatures → only 5 appended |
| `test_refine_suggestions_placement_match` | 6 | Suggestion with matching file → mapped to task |
| `test_refine_suggestions_area_match` | 6 | Suggestion area "interfaces" → API task |
| `test_refine_suggestions_unmapped_shared` | 6 | Unmatched suggestion → appended to all tasks |
| `test_orchestrator_ordering` | 7 | Steps execute in TDE-105 order |
| `test_orchestrator_all_disabled` | 7 | All config bools False → no enrichment, counters all 0 |
| `test_orchestrator_idempotent` | 7 | Run twice → same result |
| `test_orchestrator_returns_counters` | 7 | Return dict has expected keys |

### Integration Tests

| Test | What |
|------|------|
| `test_density_score_improvement` | Seed quality score increases after enrichment |
| `test_density_warnings_reduced` | Density warnings count decreases after enrichment |
| `test_enrichment_diagnostic_populated` | `IngestionDiagnostic.enrichment` is non-None with correct counters |

**Estimated test scope:** ~350 lines.

---

## Files Changed

| File | Change | Lines |
|------|--------|-------|
| `workflows/builtin/plan_ingestion_enrichment.py` | NEW — enrichment functions | ~250 |
| `workflows/builtin/plan_ingestion_workflow.py` | Wire enrichment call + diagnostic | ~30 |
| `tests/unit/workflows/test_plan_ingestion_enrichment.py` | NEW — unit tests | ~350 |
| Total | | ~630 |

No changes needed to:
- `plan_ingestion_diagnostics.py` — config fields and `EnrichmentDiagnostic` already in place
- `utils/prime_task_enrichment.py` — reused as-is for Tier 2 target file extraction

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Requirement ref proximity produces false positives | Medium | Low | Conservative default (500 chars); per-step disable via config |
| Tier 3 target file inference generates wrong paths | Medium | Medium | Tag with `_inferred: true`; downstream can filter |
| REFINE suggestion area→task heuristic mismatches | Medium | Low | Unmapped fallback distributes to all tasks; no data lost |
| Enrichment modifies task descriptions and breaks downstream parsing | Low | High | No-clobber rule (append-only); idempotent test |
| `plan_text` not available (empty string) | Low | Low | `enrich_requirement_refs` returns 0; graceful no-op |

---

## Success Criteria

After implementation, re-running plan ingestion on the run-019 Online Boutique plan should produce:

| Signal | Before | Expected After |
|--------|--------|---------------|
| Code examples | 0/6 | 3-6/6 (from API signatures) |
| Requirement refs | 0/6 | 4-6/6 (from plan text proximity) |
| Negative scope | 0/6 | 3-6/6 (already forwarded + safety net) |
| Target files | varies | 5-6/6 (Tier 1 + Tier 2 fallback) |
| Seed quality score | 0.50 | 0.65-0.80 |

---

## Cross-References

| Document | Relationship |
|----------|-------------|
| [TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md](./TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md) | Requirements: REQ-TDE-100–106, 300, 303, 400–402 |
| [KAIZEN_INVESTIGATION_RUN019](../kaizen/KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md) | Trigger: §9–10 |
| [KAIZEN_PLAN_INGESTION_IMPLEMENTATION_PLAN.md](./KAIZEN_PLAN_INGESTION_IMPLEMENTATION_PLAN.md) | Sibling: Kaizen Phase 0–3 (foundation this builds on) |
| `plan_ingestion_diagnostics.py` | Config + EnrichmentDiagnostic already defined |
| `utils/prime_task_enrichment.py` | Reuse: `extract_target_files()` for Tier 2 |
| SDK Lessons: Leg 13 #33 | Requirements layer gap — data injection ≠ prompt consumption |
| SDK Lessons: Leg 13 #40 | 12-point pipeline field threading checklist |
