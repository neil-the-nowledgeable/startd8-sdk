# Implementation Plan: Layer 3 — Shared-File Manifest (REQ-CCD-300–303)

**Status:** Ready for implementation
**Depends on:** REQ-CCD-100 (for REQ-CCD-302 only; REQ-CCD-300, 301, 303 can land independently)
**Primary file:** `src/startd8/contractors/context_seed_handlers.py`

---

## Current State

- `task.target_files` is `list[str]` on SeedTask (line 502) — relative paths like `src/utils.py`
- `compute_lanes()` at `artisan_contractor.py:1116` uses raw `target_files` strings for `file_to_idx` dict (no normalization)
- DESIGN phase context uses flat top-level keys: `context["design_results"]`, `context["design_mode_summary"]` — NOT nested under `context["design"]`
- `_CHECKPOINT_CONTEXT_KEYS` at `artisan_contractor.py:144` — frozenset of keys persisted on checkpoint
- Plan ingestion computes `shared_files: Dict[str, List[str]]` at `plan_ingestion_workflow.py:2188-2194` but only for `_file_scope` classification — not propagated to seed

---

## Context Key Convention

The requirements doc specifies `context["design"]["shared_file_manifest"]` but **no nested `context["design"]` namespace exists**. Following established convention, this plan uses flat keys: `context["shared_file_manifest"]` and `context["lane_to_file_mapping"]`.

---

## REQ-CCD-300: Build Shared-File Manifest

### Changes

**File:** `context_seed_handlers.py`

1. **New helper** (~line 860, after existing helpers):
   ```python
   def _normalize_target_path(path: str) -> str:
       """Normalize a target file path for comparison."""
       import os.path
       return os.path.normpath(path).replace("\\", "/")

   def build_shared_file_manifest(
       tasks: list[SeedTask],
   ) -> dict[str, list[str]]:
       """Build mapping from target file paths to task IDs that target them.
       Only files in 2+ tasks included."""
       file_to_tasks: dict[str, list[str]] = defaultdict(list)
       for task in tasks:
           for tf in (task.target_files or []):
               normalized = _normalize_target_path(tf)
               file_to_tasks[normalized].append(task.task_id)
       return {
           path: task_ids
           for path, task_ids in file_to_tasks.items()
           if len(task_ids) >= 2
       }
   ```

2. **Before DESIGN loop** (~line 2334):
   ```python
   shared_file_manifest: dict[str, list[str]] = {}
   try:
       shared_file_manifest = build_shared_file_manifest(tasks)
       if shared_file_manifest:
           logger.info(
               "DESIGN: %d contested file(s) across %d tasks",
               len(shared_file_manifest),
               len({tid for tids in shared_file_manifest.values() for tid in tids}),
           )
   except Exception as exc:
       logger.warning("DESIGN: manifest computation failed: %s", exc)
       shared_file_manifest = {}
   ```

### Data Structure
```python
{"src/utils.py": ["PI-003", "PI-007", "PI-011"], "src/config.py": ["PI-003", "PI-011"]}
```

### Tests
- `test_empty_tasks` → empty dict
- `test_no_overlap` → disjoint files → empty dict
- `test_two_tasks_shared_file` → correct manifest entry
- `test_path_normalization_dot_slash` → `./src/a.py` and `src/a.py` treated as same
- `test_none_target_files` → no crash

---

## REQ-CCD-301: Manifest Persistence in Design Context

### Changes

1. **After DESIGN loop** (~line 2596):
   ```python
   context["shared_file_manifest"] = shared_file_manifest
   ```

2. **`_CHECKPOINT_CONTEXT_KEYS`** at `artisan_contractor.py:144`:
   Add `"shared_file_manifest"` to the frozenset.

3. **Handoff** (`handoff.py`) — add `shared_file_manifest` parameter to `write_design_handoff()` and include in JSON.

### Tests
- `test_manifest_in_context_after_design` — verify key exists
- `test_empty_manifest_stored` — empty dict, not omitted
- `test_checkpoint_includes_manifest` — verify in checkpoint keys

---

## REQ-CCD-302: Lane-to-File Mapping

### Changes

**New function:**
```python
def compute_lane_to_file_mapping(
    lanes: list[list[SeedTask]],
    shared_file_manifest: dict[str, list[str]],
) -> dict[int, list[str]]:
    """For each lane, which shared files caused its formation."""
    mapping: dict[int, list[str]] = {}
    for lane_idx, lane_tasks in enumerate(lanes):
        lane_task_ids = {t.task_id for t in lane_tasks}
        lane_files = [
            fpath for fpath, contesting_ids in shared_file_manifest.items()
            if len(lane_task_ids & set(contesting_ids)) >= 2
        ]
        if lane_files:
            mapping[lane_idx] = sorted(lane_files)
    return mapping
```

**Integration:** After lane computation (CCD-100) + manifest computation (CCD-300):
```python
lane_to_file_mapping = compute_lane_to_file_mapping(lanes, shared_file_manifest)
context["lane_to_file_mapping"] = lane_to_file_mapping
```

### Tests
- `test_empty_lanes` → empty dict
- `test_single_lane_shared_file` → correct mapping
- `test_file_shared_across_lanes` → appears in neither lane (overlap < 2 per lane)

---

## REQ-CCD-303: Prompt Injection of Contested Files

### Changes

**In `_task_to_feature_context()`** (~line 1718, after `shared_modules` section):

```python
if shared_file_manifest and task.target_files:
    task_contested: list[str] = []
    for tf in task.target_files:
        normalized_tf = _normalize_target_path(tf)
        contesting_ids = shared_file_manifest.get(normalized_tf)
        if contesting_ids:
            others = [tid for tid in contesting_ids if tid != task.task_id]
            if others:
                other_descs = [
                    f"{tid} ({(task_title_lookup or {}).get(tid, '')})"
                    for tid in others
                ]
                task_contested.append(f"  - `{tf}`: {', '.join(other_descs)}")
    if task_contested:
        additional_context["contested_files"] = (
            "SHARED FILE WARNING: These files are targeted by multiple tasks. "
            "Coordinate your design with theirs.\n" + "\n".join(task_contested)
        )
```

**New parameter on `_task_to_feature_context()`:** `task_title_lookup: dict[str, str] | None = None`

**Call site:** Pass `task_title_lookup={t.task_id: t.title for t in tasks}` (computed once before the loop).

### Tests
- `test_no_manifest_no_injection` — `shared_file_manifest=None` → no key
- `test_contested_files_injected` — task's file in manifest → key present
- `test_self_exclusion` — current task ID not listed among "others"

---

## Implementation Sequence

1. `_normalize_target_path()` + `build_shared_file_manifest()` (REQ-CCD-300)
2. Manifest computation before DESIGN loop (REQ-CCD-300)
3. `context["shared_file_manifest"]` after loop + checkpoint key (REQ-CCD-301)
4. `shared_file_manifest` param on `_task_to_feature_context()` + contested files injection (REQ-CCD-303)
5. `compute_lane_to_file_mapping()` + integration (REQ-CCD-302 — can defer until Layer 1 lands)
6. Handoff persistence (REQ-CCD-301)

Steps 1-4 can land in one commit. Step 5 can follow with Layer 1.

---

## Test File

`tests/unit/contractors/test_shared_file_manifest.py`

Classes: `TestBuildSharedFileManifest`, `TestNormalizeTargetPath`, `TestComputeLaneToFileMapping`, `TestContestedFilePromptInjection`

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Path normalization inconsistency with `compute_lanes()` | Medium | Use same `_normalize_target_path()` helper; in practice clean relative paths |
| `shared_modules` duplication | Low | Different data sources (ContextCore vs pipeline tasks); complementary, not duplicative |
| Checkpoint schema change | None | `context.get()` with defaults handles missing keys |
