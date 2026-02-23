# Implementation Plan: Layer 1 — Lane-Aware Design Ordering (REQ-CCD-100–104)

**Status:** Ready for implementation
**Depends on:** Nothing (foundation layer)
**Primary file:** `src/startd8/contractors/context_seed_handlers.py`

---

## Current State

- `compute_lanes()` at `artisan_contractor.py:1070` — Union-Find on shared `target_files` + `depends_on`. Already exported in `__all__` (line 95). Called at IMPLEMENT time (lines 2918, 3307) but never at DESIGN time.
- `SeedTask` at `context_seed_handlers.py:491` — has `task_id`, `target_files: list[str]` (line 502), `depends_on: list[str]` (line 500), and `wave_index: Optional[int] = None` (line 532). All attributes needed by `compute_lanes()` are present.
- DESIGN loop at `context_seed_handlers.py:2335` — flat `for idx, task in enumerate(tasks, start=1):` with ~260 lines of body (3 branches: adopt, dry_run, real-mode).
- Existing imports at line 67-74 — already imports `compute_waves`, `compute_wave_index_map`, `compute_wave_metadata` from `artisan_contractor`. Does NOT import `compute_lanes`.

---

## REQ-CCD-100: Compute Lane Assignments at DESIGN Time

### Changes

**File:** `context_seed_handlers.py`

1. **Line 67-74** — Add `compute_lanes` to the existing import:
   ```python
   from startd8.contractors.artisan_contractor import (
       ...,
       compute_lanes,
       ...
   )
   ```

2. **After line ~2334, before line 2335** — Insert lane computation:
   ```python
   # CCD-100: Compute lane assignments at DESIGN time
   _design_lanes: list[list[SeedTask]] | None = None
   _lane_assignments: dict[str, int] = {}
   try:
       _design_lanes = compute_lanes(tasks)
       for _lane_idx, _lane_tasks in enumerate(_design_lanes):
           for _lt in _lane_tasks:
               _lane_assignments[_lt.task_id] = _lane_idx
       logger.info(
           "DESIGN: computed %d lane(s) for %d tasks",
           len(_design_lanes), len(tasks),
       )
   except Exception as _lane_exc:
       # CCD-104: Graceful fallback
       logger.warning(
           "DESIGN: compute_lanes() failed — falling back to flat iteration: %s",
           _lane_exc,
       )
       _design_lanes = None

   context.setdefault("design", {})
   context["design"]["lane_assignments"] = _lane_assignments
   ```

### Tests
- `test_compute_lanes_called_before_design_loop` — mock `compute_lanes`, verify called once with full task list
- `test_lane_assignments_stored_in_context` — dry_run, verify `context["design"]["lane_assignments"]` populated
- `test_single_lane_degenerate_case` — all disjoint files, verify single-lane behavior

---

## REQ-CCD-101: Wave-Sort Tasks Within Each Lane

### Changes

**File:** `context_seed_handlers.py` — immediately after CCD-100 block:

```python
# CCD-101: Wave-sort tasks within each lane
if _design_lanes is not None:
    for _li, _lane in enumerate(_design_lanes):
        _design_lanes[_li] = sorted(
            _lane,
            key=lambda t: (
                t.wave_index if t.wave_index is not None else float('inf'),
                t.task_id,
            ),
        )
```

### Tests
- `test_wave_sort_within_lane` — tasks with wave_index [2, 0, 1] sort to [0, 1, 2]
- `test_wave_sort_none_wave_at_end` — None wave_index sorts last
- `test_wave_sort_tiebreak_by_task_id` — same wave_index sorted lexicographically by task_id

---

## REQ-CCD-102: Lane-Sequential Design Iteration

### Changes

**File:** `context_seed_handlers.py` — replace line 2335.

Instead of nesting two `for` loops (which would re-indent ~260 lines), pre-compute the flattened iteration order:

```python
# CCD-102: Lane-sequential design iteration
if _design_lanes is not None:
    _iteration_order: list[tuple[int, SeedTask]] = []
    _global_idx = 0
    for _lane in _design_lanes:
        for _task in _lane:
            _global_idx += 1
            _iteration_order.append((_global_idx, _task))
else:
    # CCD-104: Flat iteration fallback
    _iteration_order = list(enumerate(tasks, start=1))

for idx, task in _iteration_order:
```

**Why pre-compute instead of nested loops:** Avoids a massive re-indentation diff of ~260 lines. The inner loop body is unchanged. The `idx` counter is continuous across lanes for progress reporting compatibility.

### Tests
- `test_lane_sequential_iteration_order` — 5 tasks in 2 lanes, verify processing order matches lane-then-wave
- `test_idx_counter_continuous_across_lanes` — idx spans 1..N without reset
- `test_all_existing_per_task_logic_preserved` — dry_run end-to-end, all tasks produce design_results entries

---

## REQ-CCD-103: Single-Source-of-Truth Lane Computation

### Changes

No code changes beyond CCD-100. This is a constraint requirement: the import of `compute_lanes` from `artisan_contractor` (not a local reimplementation) satisfies it.

### Tests
- `test_design_lanes_match_implement_lanes` — same task list produces identical lanes at DESIGN and IMPLEMENT time (trivially true, but documents the requirement)

---

## REQ-CCD-104: Graceful Fallback to Flat Iteration

### Changes

Already embedded in CCD-100 (`try/except`) and CCD-102 (`else` branch). No additional code.

### Tests
- `test_fallback_on_compute_lanes_exception` — patch `compute_lanes` to raise, verify WARNING log and all tasks still processed
- `test_fallback_on_empty_target_files` — tasks with `target_files=[]`, verify compute_lanes succeeds
- `test_no_regression_flat_iteration` — compare design_results from lane-aware vs flat (identical for disjoint-file tasks)

---

## Consolidated Change Summary

| Location | Lines Affected | Change |
|---|---|---|
| Import block | 67-74 | Add `compute_lanes` |
| Before DESIGN loop | ~2334 | +30 lines: lane computation + wave-sort + iteration-order |
| DESIGN loop head | 2335 | Replace `enumerate(tasks)` with `_iteration_order` |

**One production file, two locations, ~35 lines added.** All 5 requirements can land in a single commit.

---

## Test File

`tests/unit/contractors/test_design_lane_ordering.py` (~15 tests)

Uses `FakeSeedTask` from `conftest.py` (already has `wave_index` at line 48, `target_files`, `depends_on`).

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Iteration order change affects `prior_summaries` | Low | Intentional: same-lane tasks see each other's summaries first |
| `context["design"]` dict collision | Low | `setdefault("design", {})` is safe; no current code sets this key |
| Checkpoint resume skips lane computation | Low | Lane computation runs every `execute()` call, not persisted in checkpoint |
