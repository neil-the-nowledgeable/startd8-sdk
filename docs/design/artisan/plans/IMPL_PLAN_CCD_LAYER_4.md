# Implementation Plan: Layer 4 — Wave Metadata Propagation (REQ-CCD-400–403)

**Status:** Ready for implementation
**Depends on:** REQ-CCD-300 (for REQ-CCD-403 only; REQ-CCD-400, 401, 402 are independent)
**Primary files:**
- `src/startd8/contractors/context_seed_handlers.py`
- `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

---

## Current State

- **`SeedTask.wave_index`** at `context_seed_handlers.py:532` — `Optional[int] = None`. Already parsed with full validation (positive integer check) in `from_seed_entry()` at lines 599-614, reading `entry.get("wave_index")` from the top-level task dict. The field is populated end-to-end from plan ingestion.
- **`_assign_wave_indices()`** at `plan_ingestion_workflow.py:172` — assigns `wave_index` at the top level of each task dict (`task["wave_index"] = wave_map.get(tid, 0)` at line 195). Called at `plan_ingestion_workflow.py:2426` during the TRANSFORM phase. Returns `(tasks, wave_meta)`.
- **`_TaskDictAdapter`** at `plan_ingestion_workflow.py:134` — adapts task dicts for `compute_waves()`. Has `task_id` and `depends_on` properties but **no `target_files` property**. Task dicts store `target_files` nested under `config.context.target_files`, not at the top level.
- **Plan ingestion imports** at `plan_ingestion_workflow.py:49-54` — already imports `compute_waves`, `compute_wave_index_map`, `compute_wave_metadata` from `artisan_contractor`. Does NOT import `compute_lanes`.
- **`ArtisanContextSeed`** at `plan_ingestion_models.py:153` — has `wave_metadata: Optional[Dict[str, Any]]` (line 177) but no `lane_assignments` field.
- **Seed schema** at `plan_ingestion_workflow.py:98` — `"wave_metadata": {"type": ["object", "null"]}` exists in `_ARTISAN_SEED_SCHEMA`. No `lane_assignments` key defined.
- **`_serialize_result()`** at `context_seed_handlers.py:2118` — returns dict with keys `design_document`, `feature_name`, `agreed`, `iterations`, `completed_at`. No wave or lane metadata fields.
- **`design_results`** at `context_seed_handlers.py:2512` — written per-task as `{**serialized, "status": ..., "cost": ...}`. No wave/lane metadata.
- **DESIGN loop** at `context_seed_handlers.py:2335` — flat `for idx, task in enumerate(tasks, start=1)`. Tasks have `wave_index` populated from plan ingestion.
- **`_task_to_feature_context()`** at `context_seed_handlers.py:1635` — `@staticmethod` with 14 keyword-only params ending at `scaffold_existing_files` (line 1654). Last param is `scaffold_existing_files: list[str] | None = None`.
- **`context_seed_handlers.py` imports** at ~lines 67-74 — imports `compute_waves`, `compute_wave_index_map`, `compute_wave_metadata` from `artisan_contractor`. Does NOT import `compute_lanes`.
- **Shared-file manifest** (`build_shared_file_manifest()`) — does not yet exist (planned in REQ-CCD-300, Layer 3).
- **Critical path detection** — no current implementation. Plan ingestion `_wave_meta["critical_path_length"]` at line 3259 is set to `_wave_count` (number of waves), not derived from file contention.

---

## REQ-CCD-400: Wave Index Available at Design Time

### Context

`SeedTask.wave_index` is already populated end-to-end: plan ingestion assigns `task["wave_index"] = wave_map.get(tid, 0)` at `plan_ingestion_workflow.py:195`, and `SeedTask.from_seed_entry()` reads it at line 600. The field reaches the DESIGN loop at `context_seed_handlers.py:2335` with valid values.

The requirement's acceptance criteria state: "Tasks whose `wave_index` was computed during plan ingestion retain that value unchanged through PLAN to DESIGN." This is already true. The wave_index computation uses `compute_waves()` from `artisan_contractor.py` — the same function used at execution time.

**What is NOT yet done:** The DESIGN loop does not validate or surface this information. REQ-CCD-400's primary deliverable is a validation assertion that logs a WARNING when tasks arrive at DESIGN with `wave_index=None`, indicating that plan ingestion did not run wave assignment.

### Changes

**File:** `context_seed_handlers.py`

1. **After line ~2334, before line 2335** — Add wave_index population check:

   ```python
   # CCD-400: Validate wave_index populated at DESIGN time
   _tasks_without_wave = [t.task_id for t in tasks if t.wave_index is None]
   if _tasks_without_wave:
       logger.warning(
           "DESIGN: %d task(s) have no wave_index (plan ingestion may not have run "
           "wave assignment): %s",
           len(_tasks_without_wave),
           ", ".join(_tasks_without_wave[:10]),
       )
   else:
       _wave_distribution: dict[int, int] = {}
       for _t in tasks:
           _wi = _t.wave_index or 0
           _wave_distribution[_wi] = _wave_distribution.get(_wi, 0) + 1
       logger.info(
           "DESIGN: wave_index validated — %d tasks across %d wave(s): %s",
           len(tasks),
           len(_wave_distribution),
           dict(sorted(_wave_distribution.items())),
       )
   ```

   **Placement note:** This block lands after line 2334 (the `inv_refine_suggestions` assignment) and before the existing `for idx, task in enumerate(tasks, start=1):` at line 2335. In the Layer 1 implementation, this will land inside the block added before `_iteration_order` construction.

### Tests

- `test_wave_index_validation_all_present` — all tasks have wave_index, verify INFO log with distribution
- `test_wave_index_validation_some_missing` — 2 of 5 tasks have `wave_index=None`, verify WARNING log naming those task IDs
- `test_wave_index_validation_all_missing` — all tasks have `wave_index=None`, verify WARNING log

---

## REQ-CCD-401: Wave Metadata in Design Results

### Context

`_serialize_result()` at `context_seed_handlers.py:2118` currently returns only 5 fields. Lane and wave metadata must be added to the design result entry for each task. The lane metadata (lane_index, lane_peer_count) depends on lane computation from Layer 1 (REQ-CCD-100). However, `wave_index` is already available on `task.wave_index` right now, so a partial implementation is possible without Layer 1.

The `shared_file_count` field depends on the shared-file manifest from REQ-CCD-300 (Layer 3). For a standalone Layer 4 implementation, `shared_file_count` defaults to 0 when the manifest is not yet present.

### Changes

**File:** `context_seed_handlers.py`

1. **Lines 2509-2512** — Extend the successful design result dict. Currently:
   ```python
   serialized = self._serialize_result(result)
   serialized["status"] = "refined" if prior_design_text else "designed"
   serialized["cost"] = task_cost
   design_results[task.task_id] = serialized
   ```

   After CCD-401, append wave/lane metadata immediately after:
   ```python
   # CCD-401: Wave and lane metadata in design results
   design_results[task.task_id]["wave_index"] = task.wave_index
   design_results[task.task_id]["lane_index"] = _lane_assignments.get(task.task_id, 0)
   design_results[task.task_id]["lane_peer_count"] = (
       len(_design_lanes[_lane_assignments[task.task_id]]) - 1
       if _design_lanes and task.task_id in _lane_assignments
       else len(tasks) - 1  # fallback: all tasks in one virtual lane
   )
   design_results[task.task_id]["shared_file_count"] = len([
       f for f in task.target_files
       if f in (shared_file_manifest or {})
   ])
   design_results[task.task_id]["critical_path"] = False  # populated by CCD-403
   ```

   **Dependency note:** `_lane_assignments` and `_design_lanes` come from Layer 1 (REQ-CCD-100). `shared_file_manifest` comes from Layer 3 (REQ-CCD-300). Before those layers land, use sentinel defaults:
   - `_lane_assignments = {}` (no lanes computed)
   - `_design_lanes = None`
   - `shared_file_manifest = {}` (empty manifest)

2. **Adopted path at lines 2397-2444** — The adopted result is a copy of `prior` dict. Add wave/lane metadata here too:
   ```python
   design_results[task.task_id] = {**prior, "status": "adopted", ...}
   # CCD-401: Update wave/lane metadata even for adopted results
   design_results[task.task_id]["wave_index"] = task.wave_index
   design_results[task.task_id]["lane_index"] = _lane_assignments.get(task.task_id, 0)
   design_results[task.task_id]["lane_peer_count"] = (
       len(_design_lanes[_lane_assignments[task.task_id]]) - 1
       if _design_lanes and task.task_id in _lane_assignments
       else len(tasks) - 1
   )
   design_results[task.task_id]["shared_file_count"] = len([
       f for f in task.target_files
       if f in (shared_file_manifest or {})
   ])
   design_results[task.task_id]["critical_path"] = False
   ```

   **Placement:** After line 2402 (`tasks_adopted += 1`) and before the `prior.get("agreed")` check at line 2403.

3. **`_serialize_result()`** — No change to the static method itself. The wave/lane metadata is added inline at the call site, not inside the serializer. This avoids passing `task` and other state into a method that currently takes only `result`.

### Tests

- `test_design_result_has_wave_index` — designed task, verify `design_results["T-1"]["wave_index"]` matches `task.wave_index`
- `test_design_result_wave_index_none` — task with no wave_index, verify key present with value `None`
- `test_design_result_has_lane_index_zero_without_layer1` — before Layer 1, `lane_index=0`
- `test_design_result_has_lane_peer_count` — with layer1 `_lane_assignments` populated, verify correct count
- `test_design_result_has_shared_file_count_zero_without_layer3` — no manifest, count is 0
- `test_design_result_adopted_has_metadata` — adopted path also carries wave metadata
- `test_design_result_critical_path_default_false` — `critical_path` key present and False before CCD-403 runs

---

## REQ-CCD-402: Lane Computation in Plan Ingestion

### Context

`_TaskDictAdapter` at `plan_ingestion_workflow.py:134` has only `task_id` and `depends_on` properties. `compute_lanes()` from `artisan_contractor.py` reads `task.target_files` as an attribute, which `_TaskDictAdapter` does not expose. Task dicts in plan ingestion store `target_files` at `config.context.target_files`.

This means calling `compute_lanes()` with raw `_TaskDictAdapter` objects will fail silently — `compute_lanes()` accesses `task.target_files or []` and will get `AttributeError` for each task, causing the Union-Find to never merge by file (lanes will only form by `depends_on`).

The fix requires extending `_TaskDictAdapter` with a `target_files` property that reads from `config.context.target_files`.

### Changes

**File:** `plan_ingestion_workflow.py`

1. **`_TaskDictAdapter` at line 134** — Add `target_files` property after `depends_on`:

   ```python
   @property
   def target_files(self) -> list[str]:
       """Read target_files from config.context (compute_lanes() protocol)."""
       return self._data.get("config", {}).get("context", {}).get(
           "target_files", []
       ) or []
   ```

   **Why here:** `compute_lanes()` requires `task.target_files` (line 1115 in artisan_contractor). Adding it to `_TaskDictAdapter` makes the adapter fully satisfy both `WaveComputeTask` and `compute_lanes()`'s informal protocol without a new class.

2. **After `_assign_wave_indices()` at line 172** — Add companion `_assign_lane_indices()` function (after line 197):

   ```python
   def _assign_lane_indices(
       tasks: List[Dict[str, Any]],
   ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
       """Assign lane_index to each task dict based on shared target_files.

       Delegates to compute_lanes() via _TaskDictAdapter objects.
       Lane indices are advisory — target_files may be incomplete at
       plan ingestion time (populated later during PLAN/SCAFFOLD).

       Returns:
           (tasks, lane_assignments) — tasks with lane_index added
           (at top level), and lane_assignments dict (task_id → lane_index).
           When compute_lanes() fails or target_files are all empty,
           lane_assignments is {} and no lane_index keys are added.
       """
       if not tasks:
           return tasks, {}

       adapters = [_TaskDictAdapter(t) for t in tasks]
       try:
           lanes = compute_lanes(adapters)
       except Exception as exc:
           logger.warning(
               "Lane assignment skipped (compute_lanes() failed): %s", exc
           )
           return tasks, {}

       lane_assignments: dict[str, int] = {}
       for lane_idx, lane_tasks in enumerate(lanes):
           for adapter in lane_tasks:
               lane_assignments[adapter.task_id] = lane_idx

       for task in tasks:
           tid = task.get("task_id", "")
           if tid in lane_assignments:
               task["lane_index"] = lane_assignments[tid]

       return tasks, lane_assignments
   ```

3. **Import addition** at `plan_ingestion_workflow.py:49-54`:
   ```python
   from ...contractors.artisan_contractor import (
       ...,
       compute_lanes,           # CCD-402
       ...,
   )
   ```

4. **TRANSFORM phase at line 2426** — Call `_assign_lane_indices()` after `_assign_wave_indices()`:

   ```python
   # ── Wave assignment: BFS dependency-depth layering ──
   tasks, wave_metadata = _assign_wave_indices(tasks)
   logger.info(
       "Wave assignment: %d waves for %d tasks (critical path: %d)",
       wave_metadata.get("wave_count", 0),
       len(tasks),
       wave_metadata.get("critical_path_length", 0),
   )

   # CCD-402: Lane assignment: Union-Find on shared target_files (advisory)
   tasks, lane_assignments = _assign_lane_indices(tasks)
   if lane_assignments:
       _lane_count = len(set(lane_assignments.values()))
       logger.info(
           "Lane assignment: %d lane(s) for %d tasks (advisory — "
           "target_files may be incomplete at ingestion time)",
           _lane_count,
           len(tasks),
       )
   ```

5. **`ArtisanContextSeed` at `plan_ingestion_models.py:153`** — Add `lane_assignments` field after `wave_metadata`:

   ```python
   # Lane computation metadata (task_id → lane_index). Advisory only.
   # None when target_files were not available at ingestion time.
   lane_assignments: Optional[Dict[str, int]] = None
   ```

6. **`ArtisanContextSeed.to_dict()` at `plan_ingestion_models.py:181`** — Add persistence:
   ```python
   if self.lane_assignments is not None:
       d["lane_assignments"] = self.lane_assignments
   ```

7. **Emit phase at `plan_ingestion_workflow.py:3264`** — Pass `lane_assignments` to seed construction:
   ```python
   seed = ArtisanContextSeed(
       ...,
       wave_metadata=_wave_meta,
       lane_assignments=lane_assignments if lane_assignments else None,
       ...
   )
   ```

   `lane_assignments` must be carried from the TRANSFORM step into the EMIT step. Add it to the workflow state dict that bridges these two steps.

8. **`_ARTISAN_SEED_SCHEMA` at `plan_ingestion_workflow.py:67`** — Add `lane_assignments` to schema:
   ```python
   "lane_assignments": {"type": ["object", "null"]},
   ```

9. **`SeedTask.from_seed_entry()` cross-check** — `lane_index` is now available in the task dict as `task["lane_index"]`. `SeedTask` has no `lane_index` field currently. Do NOT add it to `SeedTask` in this layer — DESIGN will recompute lanes using `compute_lanes()` (REQ-CCD-100). The seed field is advisory only.

### Tests

- `test_task_dict_adapter_target_files_from_context` — adapter reads from `config.context.target_files`
- `test_task_dict_adapter_target_files_empty_default` — missing key → empty list, no error
- `test_assign_lane_indices_basic` — two tasks sharing a file get same lane_index
- `test_assign_lane_indices_disjoint` — tasks with distinct files get different lane_indices
- `test_assign_lane_indices_no_target_files` — all tasks have empty target_files → returns `{}`, no crash
- `test_assign_lane_indices_exception_fallback` — patch `compute_lanes` to raise → WARNING log, returns `{}`
- `test_assign_lane_indices_empty_tasks` — empty input → `([], {})`
- `test_lane_assignments_written_to_seed` — end-to-end emit, seed dict has `lane_assignments` key
- `test_lane_assignments_none_when_empty` — no shared files → `lane_assignments` is `None` in seed
- `test_seed_schema_allows_lane_assignments` — schema validates with `lane_assignments` present

---

## REQ-CCD-403: Critical-Path Task Detection

### Context

This requirement depends on the shared-file manifest from REQ-CCD-300 (Layer 3). After the manifest is built, tasks with the highest "contention score" — the sum count of other tasks contesting their target files — are logged as critical path candidates. The top 20% threshold (or configurable) drives an annotation in `design_results` (`critical_path: True`).

This is **purely informational** in the initial implementation. No behavioral change.

### Changes

**File:** `context_seed_handlers.py`

1. **New helper function** (add ~line 870, after `build_shared_file_manifest()` from Layer 3):

   ```python
   def compute_critical_path_tasks(
       tasks: list,
       shared_file_manifest: dict[str, list[str]],
       top_fraction: float = 0.20,
   ) -> set[str]:
       """Identify tasks with highest shared-file contention score.

       Contention score = sum of (len(contesting_task_ids) - 1) across
       all of a task's target files that appear in the manifest.

       Args:
           tasks: List of SeedTask objects.
           shared_file_manifest: From build_shared_file_manifest() — maps
               file_path → list of contesting task_ids.
           top_fraction: Tasks in the top N% by contention score are
               flagged as critical. Default: 0.20 (top 20%).

       Returns:
           Set of task_ids identified as critical path.
       """
       if not tasks or not shared_file_manifest:
           return set()

       # Build per-task contention scores
       scores: dict[str, int] = {}
       for task in tasks:
           score = 0
           for tf in (task.target_files or []):
               normalized = _normalize_target_path(tf)
               contesting = shared_file_manifest.get(normalized, [])
               # Other tasks contesting this file (exclude self)
               score += max(0, len(contesting) - 1)
           scores[task.task_id] = score

       # Only score tasks that have any contention
       contested_scores = [s for s in scores.values() if s > 0]
       if not contested_scores:
           return set()

       # Identify top N% by contention score
       threshold_idx = max(0, int(len(contested_scores) * (1 - top_fraction)))
       sorted_scores = sorted(contested_scores)
       score_threshold = sorted_scores[threshold_idx] if threshold_idx < len(sorted_scores) else sorted_scores[-1]

       return {
           tid for tid, score in scores.items()
           if score >= score_threshold and score > 0
       }
   ```

2. **Before DESIGN loop** (~line 2334, after manifest computation from Layer 3):

   ```python
   # CCD-403: Critical-path task detection
   _critical_task_ids: set[str] = set()
   try:
       _critical_task_ids = compute_critical_path_tasks(tasks, shared_file_manifest)
       if _critical_task_ids:
           logger.info(
               "DESIGN: %d critical-path task(s) identified by shared-file "
               "contention: %s",
               len(_critical_task_ids),
               ", ".join(sorted(_critical_task_ids)),
           )
   except Exception as _crit_exc:
       logger.warning(
           "DESIGN: critical-path detection failed: %s", _crit_exc
       )
   ```

3. **In the per-task result writing** — Update `critical_path` annotation from `False` to actual value:

   In the adopted path (after line 2402):
   ```python
   design_results[task.task_id]["critical_path"] = task.task_id in _critical_task_ids
   ```

   In the freshly designed path (after line 2512):
   ```python
   design_results[task.task_id]["critical_path"] = task.task_id in _critical_task_ids
   ```

   This supersedes the `critical_path = False` default added by REQ-CCD-401.

4. **Initialization** — Before the DESIGN loop, `_critical_task_ids` defaults to `set()` so it is defined even when manifest computation fails.

### Integration with CCD-401

The `critical_path` field in `design_results` (from CCD-401) is initially written as `False`. CCD-403 overwrites it with the computed value. When CCD-403's helper is not yet implemented (e.g., standalone CCD-401 commit), the `False` default is correct per the spec: "No behavioral change in the initial implementation."

### Tests

- `test_critical_path_empty_manifest` — empty manifest → empty set
- `test_critical_path_no_shared_files` — all tasks have unique files → empty set
- `test_critical_path_top_20_percent` — 10 tasks, 2 have contention, verify top 20% flagged
- `test_critical_path_contention_score_calculation` — task with 3 contested files scored correctly
- `test_critical_path_self_excluded_from_score` — task does not count itself in contention
- `test_critical_path_annotation_in_design_results` — DESIGN loop, verify `critical_path=True` for flagged task
- `test_critical_path_annotation_adopted_path` — adopted design also gets annotation
- `test_critical_path_exception_fallback` — patch `compute_critical_path_tasks` to raise → WARNING, no crash, `_critical_task_ids=set()`

---

## Implementation Sequence

Layer 4 is decomposed into three groups, ordered by dependencies:

**Group A — Wave validation (CCD-400, CCD-401 partial):** Can land immediately, no other layer deps.
1. Add wave_index validation block before DESIGN loop (CCD-400)
2. Add `wave_index` and `lane_index=0` defaults to design result writes, both adopted and fresh paths (CCD-401 partial — wave only, lane defaults)

**Group B — Plan ingestion lane computation (CCD-402):** Independent of Groups A/C.
1. Add `target_files` property to `_TaskDictAdapter`
2. Add `_assign_lane_indices()` function after `_assign_wave_indices()`
3. Import `compute_lanes` in plan_ingestion_workflow.py
4. Wire `_assign_lane_indices()` call in the TRANSFORM phase
5. Add `lane_assignments` to `ArtisanContextSeed` and its `to_dict()`
6. Carry `lane_assignments` through to the EMIT phase
7. Update seed schema

**Group C — Critical path detection (CCD-403):** Depends on REQ-CCD-300 (Layer 3) for the manifest. Can use `shared_file_manifest = {}` fallback until Layer 3 lands.
1. Add `compute_critical_path_tasks()` helper (alongside `build_shared_file_manifest()` from Layer 3)
2. Add critical path detection block before DESIGN loop
3. Update `critical_path` annotation at both design result write sites

**Group D — Full CCD-401 lane metadata:** Depends on Layer 1 for `_lane_assignments` and `_design_lanes`.
1. Update `lane_index` and `lane_peer_count` fields in design results to use actual lane data once Layer 1 lands

Recommended commit ordering:
1. `feat(CCD-400): wave_index validation at DESIGN time` — Group A step 1
2. `feat(CCD-401): wave/lane metadata in design results (baseline)` — Group A step 2
3. `feat(CCD-402): lane computation in plan ingestion` — Group B steps 1-7
4. `feat(CCD-403): critical-path task detection by file contention` — Group C steps 1-3

---

## Consolidated Change Summary

| Location | Lines Affected | Change |
|---|---|---|
| `context_seed_handlers.py` import block | ~67-74 | No change needed — `compute_lanes` already imported by Layer 1 |
| Before DESIGN loop | ~2334 | +12 lines: wave_index validation (CCD-400) + critical path detection (CCD-403) |
| Adopted path | ~2402-2404 | +6 lines: wave/lane metadata + critical_path annotation (CCD-401) |
| Fresh design path | ~2512 | +6 lines: wave/lane metadata + critical_path annotation (CCD-401) |
| New helper | ~870 | +35 lines: `compute_critical_path_tasks()` (CCD-403) |
| `plan_ingestion_workflow.py` imports | 49-54 | +1 line: add `compute_lanes` |
| `_TaskDictAdapter` | 134-169 | +5 lines: add `target_files` property (CCD-402) |
| After `_assign_wave_indices()` | ~197 | +25 lines: `_assign_lane_indices()` (CCD-402) |
| TRANSFORM phase | ~2426-2434 | +8 lines: call `_assign_lane_indices()` (CCD-402) |
| `plan_ingestion_models.py` | ~177 | +3 lines: `lane_assignments` field + `to_dict()` (CCD-402) |
| Emit phase | ~3264-3282 | +1 line: pass `lane_assignments` to seed (CCD-402) |
| Seed schema | ~98 | +1 line: `"lane_assignments"` schema entry (CCD-402) |

**Two production files, ~100 lines net addition.** Four requirements can land in three commits.

---

## Test File

`tests/unit/contractors/test_ccd_layer4_wave_metadata.py`

Classes:
- `TestWaveIndexValidation` — CCD-400 (3 tests)
- `TestDesignResultWaveMetadata` — CCD-401 (7 tests)
- `TestLaneComputationPlanIngestion` — CCD-402 (10 tests)
- `TestCriticalPathDetection` — CCD-403 (8 tests)

Uses `FakeSeedTask` from `tests/unit/contractors/conftest.py` (already has `wave_index` at line 48, `target_files` at line 25, `depends_on` at line 23).

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `_TaskDictAdapter.target_files` reads from wrong path | Medium | Task dicts nest under `config.context.target_files` — verified at `plan_ingestion_workflow.py:2462`. The property reads `self._data.get("config", {}).get("context", {}).get("target_files", [])`. Unit test verifies the path. |
| `compute_lanes()` called with adapters that have `target_files=[]` everywhere | Low | When `target_files` are not yet populated at ingestion time, `compute_lanes()` degenerates to `depends_on`-only grouping. Result is a valid (if incomplete) lane assignment. Log message marks advisory nature. |
| CCD-401 `lane_peer_count` wrong before Layer 1 | Low | Sentinel default `len(tasks) - 1` (all tasks in one virtual lane) is clearly wrong but harmlessly conservative. Layer 1 replaces it with accurate values. |
| `critical_path` `False` default overwritten at wrong location | Low | CCD-403 overwrites the `False` default set by CCD-401. Both are in the same code path; CCD-403's write must come AFTER the `design_results[task.task_id]` dict is established. |
| `lane_assignments` dict not carried from TRANSFORM to EMIT in plan ingestion | Medium | The TRANSFORM step returns `tasks` only. `lane_assignments` must be returned alongside or stored in workflow state. Prefer returning a tuple `(tasks, lane_assignments)` and threading to EMIT. Verify call chain before implementing. |
| Seed schema change breaks downstream consumers | None | `additionalProperties: True` at schema line 101 means new optional fields never cause validation failure. Schema addition is additive-only. |

---

## Relationship to Other Layers

| This Layer | Other Layer | Relationship |
|---|---|---|
| CCD-400 wave validation | CCD-101 (Layer 1, wave-sort) | CCD-101 reads `task.wave_index` directly. CCD-400's validation block documents and logs when this sort is degraded. |
| CCD-401 design_results enrichment | CCD-100 (Layer 1) for `_lane_assignments` | Before Layer 1 lands, `lane_index=0` and `lane_peer_count=len(tasks)-1` are correct-but-unknown sentinels. |
| CCD-401 `shared_file_count` | CCD-300 (Layer 3) for `shared_file_manifest` | Before Layer 3 lands, `shared_file_count=0` is a correct-but-unknown default. |
| CCD-402 `lane_assignments` in seed | Advisory input to CCD-100 (Layer 1) | DESIGN re-computes lanes from the final task list (CCD-100). The seed value is only a cross-check. |
| CCD-403 critical path | CCD-300 (Layer 3) for manifest | Without manifest, `compute_critical_path_tasks()` returns empty set — no annotations. |
| CCD-403 `critical_path` annotation | CCD-401 `critical_path` field | CCD-401 initializes `False`; CCD-403 overwrites with computed value. |
