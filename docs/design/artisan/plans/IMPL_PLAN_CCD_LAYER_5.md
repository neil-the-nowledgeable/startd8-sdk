# Implementation Plan: Layer 5 — Design Collision Detection (REQ-CCD-500–503)

**Status:** Ready for implementation
**Depends on:** Layer 1 (REQ-CCD-100–104), Layer 2 (REQ-CCD-200–205), Layer 3 (REQ-CCD-300–303)
**Primary file:** `src/startd8/contractors/context_seed_handlers.py`
**New module:** `src/startd8/contractors/design_collision.py`

---

## Current State

- DESIGN loop at `context_seed_handlers.py:2335` — flat `for idx, task in enumerate(tasks, start=1):` produces `design_results` dict keyed by `task_id`. After Layer 1 this becomes lane-sequential iteration. After Layer 3 `shared_file_manifest` is computed before the loop.
- `context["design_results"]` written at line 2596. `context["design_mode_summary"]` (per-task `"create"` / `"update"` / `"skipped"`) written at line 2606.
- No post-loop compatibility check exists. `context["lane_conflicts"]` key does not exist.
- `edit_first_gate.py` at `src/startd8/contractors/edit_first_gate.py` — `EditFirstGateResult`, `resolve_threshold()`, and `check_file()` operate independently of design-time collision data.
- `HandlerConfig` dataclass at line 404 has ~22 fields. No `design_collision_strategy` field exists.
- `_CHECKPOINT_CONTEXT_KEYS` at `artisan_contractor.py:144` — frozenset of 28 keys. Does not include `lane_conflicts`.
- `ImplementPhaseHandler.execute()` at line 2673 — reads `design_results`, `design_mode_summary`, and other context keys. No lane_conflicts read path exists.
- `_task_to_feature_context()` at line 1634 — `@staticmethod` with 16 keyword-only params, returns `FeatureContext`. No collision context param exists.
- `re` module already imported at line 56. `defaultdict` already imported at line 62.

---

## New Module: `src/startd8/contractors/design_collision.py`

All collision detection logic is extracted into a standalone module. This keeps `context_seed_handlers.py` clean and makes the collision module independently testable.

### Module Structure

```python
"""Design Collision Detection for the Artisan DESIGN phase (REQ-CCD-500–503).

Heuristic-based compatibility check across design documents within a lane.
All checks are string/regex based — no LLM calls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from startd8.logging_config import get_logger

logger = get_logger(__name__)
```

---

## REQ-CCD-502: Collision Severity Classification

### CollisionSeverity Enum

```python
class CollisionSeverity(str, Enum):
    """Severity of a detected design collision.

    COHERENT    — No conflicts detected within the lane.
    WARNING     — Potential conflict (e.g., create+update mode mismatch, uncertain
                  duplicate name match). Implementation should proceed with caution.
    CONFLICTING — Definite conflict (e.g., two tasks both create the same file from
                  scratch, or two tasks define the same class name for the same file).
    """
    COHERENT = "COHERENT"
    WARNING = "WARNING"
    CONFLICTING = "CONFLICTING"
```

### Data Structures

```python
@dataclass
class DesignCollision:
    """A single detected collision between two task designs."""
    file_path: str          # Shared file where the collision was detected
    task_a: str             # task_id of first task
    task_b: str             # task_id of second task
    conflict_type: str      # "mode_conflict" | "duplicate_class" | "duplicate_function" | "mode_double_create"
    severity: CollisionSeverity
    detail: str             # Human-readable description


@dataclass
class LaneCollisionResult:
    """Post-lane compatibility check result for a single lane."""
    lane_index: int
    task_ids: list[str]
    shared_files: list[str]
    collisions: list[DesignCollision] = field(default_factory=list)
    status: CollisionSeverity = CollisionSeverity.COHERENT

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for context propagation."""
        return {
            "lane_index": self.lane_index,
            "task_ids": self.task_ids,
            "shared_files": self.shared_files,
            "collisions": [
                {
                    "file_path": c.file_path,
                    "task_a": c.task_a,
                    "task_b": c.task_b,
                    "conflict_type": c.conflict_type,
                    "severity": c.severity.value,
                    "detail": c.detail,
                }
                for c in self.collisions
            ],
            "status": self.status.value,
        }
```

### Context Key

`context["lane_conflicts"]` is a `list[dict]` where each dict is the output of `LaneCollisionResult.to_dict()`. Format:

```python
[
    {
        "lane_index": 1,
        "task_ids": ["PI-003", "PI-007"],
        "shared_files": ["src/utils.py"],
        "collisions": [
            {
                "file_path": "src/utils.py",
                "task_a": "PI-003",
                "task_b": "PI-007",
                "conflict_type": "mode_double_create",
                "severity": "CONFLICTING",
                "detail": "Both tasks plan to CREATE src/utils.py from scratch...",
            }
        ],
        "status": "CONFLICTING",
    }
]
```

### Checkpoint Key

Add `"lane_conflicts"` to `_CHECKPOINT_CONTEXT_KEYS` at `artisan_contractor.py:144`.

### Tests

- `test_lane_conflicts_written_to_context` — dry_run=True with 2 tasks sharing a file, verify `context["lane_conflicts"]` is a list
- `test_lane_conflicts_empty_on_fallback` — mock `compute_lanes()` to raise, verify `context["lane_conflicts"] == []`
- `test_conflicting_task_ids_logged_in_implement` — mock context with conflicting entry, verify WARNING log in IMPLEMENT handler

---

## REQ-CCD-500: Post-Lane Compatibility Check

### Entity Extraction

Regex-based extraction of class names, function signatures, and imports from a design document. This is heuristic — it scans for common Python patterns in design text.

```python
# Patterns for entity extraction
_CLASS_PATTERN = re.compile(r"^\s*(?:class|Class)\s+([A-Z][A-Za-z0-9_]+)", re.MULTILINE)
_FUNC_PATTERN = re.compile(r"^\s*(?:def|function)\s+([a-z_][A-Za-z0-9_]+)\s*\(", re.MULTILINE)
_IMPORT_PATTERN = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)", re.MULTILINE)

def extract_entities(design_text: str) -> dict[str, set[str]]:
    """Extract named entities from a design document.

    Returns:
        Dict with keys "classes", "functions", "imports" — each a set of
        extracted names/paths. Empty sets when text has no matching patterns.
    """
    if not design_text:
        return {"classes": set(), "functions": set(), "imports": set()}
    return {
        "classes":   set(_CLASS_PATTERN.findall(design_text)),
        "functions": set(_FUNC_PATTERN.findall(design_text)),
        "imports":   set(_IMPORT_PATTERN.findall(design_text)),
    }
```

### Main Function

```python
def check_lane_collisions(
    lane_index: int,
    lane_tasks: list,   # list[SeedTask] — avoids circular import
    design_results: dict[str, dict[str, Any]],
    shared_file_manifest: dict[str, list[str]],
    design_mode_summary: dict[str, str],
) -> LaneCollisionResult:
    """Run post-lane compatibility check for a single lane.

    For each shared file in the lane, extract entities from each task's
    design document and check for duplicate class/function definitions.
    Also checks design_mode_summary for create/update conflicts (REQ-CCD-501).
    """
    lane_task_ids = [t.task_id for t in lane_tasks]
    # Identify shared files that involve 2+ tasks in THIS lane
    lane_shared_files: list[str] = [
        fpath for fpath, contesting in shared_file_manifest.items()
        if len(set(contesting) & set(lane_task_ids)) >= 2
    ]

    result = LaneCollisionResult(
        lane_index=lane_index,
        task_ids=lane_task_ids,
        shared_files=lane_shared_files,
    )

    if not lane_shared_files:
        return result  # No shared files → COHERENT by definition

    # Build per-task entity map
    task_entities: dict[str, dict[str, set[str]]] = {}
    for tid in lane_task_ids:
        dr = design_results.get(tid, {})
        doc_text = dr.get("design_document", "")
        task_entities[tid] = extract_entities(doc_text)

    for fpath in lane_shared_files:
        contesting_in_lane = [
            tid for tid in (shared_file_manifest.get(fpath) or [])
            if tid in lane_task_ids
        ]
        if len(contesting_in_lane) < 2:
            continue

        # Mode conflict detection (REQ-CCD-501) — pairwise
        _check_mode_conflicts(fpath, contesting_in_lane, design_mode_summary, result)

        # Entity collision detection — pairwise class/function duplicates
        _check_entity_collisions(fpath, contesting_in_lane, task_entities, result)

    # Determine overall lane status from worst collision seen
    if any(c.severity == CollisionSeverity.CONFLICTING for c in result.collisions):
        result.status = CollisionSeverity.CONFLICTING
    elif any(c.severity == CollisionSeverity.WARNING for c in result.collisions):
        result.status = CollisionSeverity.WARNING
    else:
        result.status = CollisionSeverity.COHERENT

    return result
```

### Entity Collision Helper

```python
def _check_entity_collisions(
    fpath: str,
    task_ids: list[str],
    task_entities: dict[str, dict[str, set[str]]],
    result: LaneCollisionResult,
) -> None:
    """Pairwise duplicate class/function detection for a shared file."""
    for i in range(len(task_ids)):
        for j in range(i + 1, len(task_ids)):
            ta, tb = task_ids[i], task_ids[j]
            ents_a = task_entities.get(ta, {})
            ents_b = task_entities.get(tb, {})

            for etype in ("classes", "functions"):
                shared = ents_a.get(etype, set()) & ents_b.get(etype, set())
                if shared:
                    result.collisions.append(DesignCollision(
                        file_path=fpath,
                        task_a=ta,
                        task_b=tb,
                        conflict_type=f"duplicate_{etype[:-1]}",
                        severity=CollisionSeverity.WARNING,
                        detail=(
                            f"Both tasks define {etype} {sorted(shared)} "
                            f"in {fpath}. Verify they are identical definitions "
                            f"or designed for non-overlapping scopes."
                        ),
                    ))
```

Note: duplicate entities are classified as `WARNING` (not `CONFLICTING`) because the same class/function name in two design docs may be intentional (e.g., one adds a method to an existing class, the other defines the same class for reference). Mode-based conflicts are the primary `CONFLICTING` signal (REQ-CCD-501).

### Integration in `context_seed_handlers.py`

**After line 2625** (after `context["design_mode_summary"]` is fully computed, before `DesignPhaseOutput` validation):

```python
# CCD-500: Post-lane compatibility check (uses fully computed design_mode_summary)
from startd8.contractors.design_collision import check_lane_collisions

_lane_conflicts: list[dict[str, Any]] = []
if _design_lanes is not None:
    for _li, _lane_tasks in enumerate(_design_lanes):
        _lc = check_lane_collisions(
            lane_index=_li,
            lane_tasks=_lane_tasks,
            design_results=design_results,
            shared_file_manifest=shared_file_manifest,
            design_mode_summary=context["design_mode_summary"],
        )
        _lane_conflicts.append(_lc.to_dict())
else:
    # CCD-104 fallback: no lane computation → no collision check
    logger.info("DESIGN: lane computation not performed — skipping collision check")
context["lane_conflicts"] = _lane_conflicts
```

### Tests

- `test_check_lane_collisions_no_shared_files` — lane with 2 tasks, disjoint files → `COHERENT`, empty collisions
- `test_check_lane_collisions_detects_duplicate_class` — task A and B both have `class MetricCollector` → `WARNING`
- `test_check_lane_collisions_detects_duplicate_function` — both tasks mention `def process()` → `WARNING`
- `test_check_lane_collisions_no_doc_text` — design result is `design_failed` → no false collision, returns `COHERENT`
- `test_extract_entities_empty` — empty string → all empty sets
- `test_extract_entities_class_and_func` — multiline text with class and def patterns → correct extraction
- `test_lane_collision_result_to_dict` — serialization format matches expected JSON structure
- `test_worst_severity_wins` — lane with WARNING and CONFLICTING collisions → overall `CONFLICTING`

---

## REQ-CCD-501: Design Mode Conflict Detection

### Overview

Two sub-cases:
1. `create` + `update` for the same file → `WARNING` (one task plans to create from scratch, other expects file to exist)
2. `create` + `create` for the same file → `CONFLICTING` (both try to create the file from scratch — destructive collision)
3. `update` + `update` → `INFO` log only, no collision record (both edit existing file — normal lane behavior)

### Helper Function

```python
def _check_mode_conflicts(
    fpath: str,
    task_ids: list[str],
    design_mode_summary: dict[str, str],
    result: LaneCollisionResult,
) -> None:
    """Check for design_mode conflicts among tasks contesting a shared file.

    REQ-CCD-501:
    - create + update → WARNING
    - create + create → CONFLICTING
    - update + update → INFO log only (not a conflict record)
    """
    creators = [tid for tid in task_ids if design_mode_summary.get(tid) == "create"]
    updaters = [tid for tid in task_ids if design_mode_summary.get(tid) == "update"]

    # Two creators for same file: both would overwrite the file from scratch
    if len(creators) >= 2:
        for i in range(len(creators)):
            for j in range(i + 1, len(creators)):
                result.collisions.append(DesignCollision(
                    file_path=fpath,
                    task_a=creators[i],
                    task_b=creators[j],
                    conflict_type="mode_double_create",
                    severity=CollisionSeverity.CONFLICTING,
                    detail=(
                        f"Both tasks plan to CREATE {fpath} from scratch. "
                        f"Second write will clobber the first. "
                        f"One task should be redesigned to use 'update' mode."
                    ),
                ))

    # Create + update: create assumes file doesn't exist, update assumes it does
    for creator in creators:
        for updater in updaters:
            result.collisions.append(DesignCollision(
                file_path=fpath,
                task_a=creator,
                task_b=updater,
                conflict_type="mode_conflict",
                severity=CollisionSeverity.WARNING,
                detail=(
                    f"Task {creator} plans to CREATE {fpath} while "
                    f"task {updater} plans to UPDATE it. Verify ordering "
                    f"and that the create task runs first."
                ),
            ))

    # update + update: informational only
    if len(updaters) >= 2 and not creators:
        logger.info(
            "DESIGN CCD-501: %d tasks update shared file %s — "
            "lane-peer context should prevent interface conflicts",
            len(updaters), fpath,
        )
```

### Tests

- `test_mode_conflict_create_plus_update` — task A=create, task B=update → `WARNING`
- `test_mode_conflict_double_create` — task A=create, task B=create → `CONFLICTING`
- `test_mode_conflict_double_update_no_collision` — task A=update, task B=update → no collision record, INFO log
- `test_mode_conflict_skipped_tasks_excluded` — task with `design_mode_summary=="skipped"` not treated as creator or updater
- `test_mode_conflict_pairwise_all_combinations` — 3 tasks: 2 creators + 1 updater → 1 CONFLICTING + 2 WARNINGs

---

## REQ-CCD-503: Collision Resolution Strategy

### HandlerConfig Extension

**File:** `context_seed_handlers.py` — `HandlerConfig` at line ~430:

```python
# CCD-503: Collision resolution strategy
design_collision_strategy: str = "warn"  # "warn" | "redesign" | "abort"
```

Add validation in `__post_init__`:

```python
_VALID_COLLISION_STRATEGIES = frozenset({"warn", "redesign", "abort"})

def __post_init__(self) -> None:
    ...
    if self.design_collision_strategy not in _VALID_COLLISION_STRATEGIES:
        raise ValueError(
            f"design_collision_strategy must be one of "
            f"{sorted(_VALID_COLLISION_STRATEGIES)}; "
            f"got {self.design_collision_strategy!r}"
        )
```

### Resolution Logic

Placed immediately after the collision check block, before `DesignPhaseOutput` validation:

```python
# CCD-503: Apply collision resolution strategy
from startd8.contractors.design_collision import CollisionSeverity

_strategy = self.config.design_collision_strategy
_conflicting_lanes = [
    lc for lc in _lane_conflicts
    if lc.get("status") == CollisionSeverity.CONFLICTING.value
]

if _conflicting_lanes:
    if _strategy == "warn":
        logger.warning(
            "DESIGN CCD-503 [warn]: %d lane(s) have CONFLICTING designs. "
            "IMPLEMENT will receive collision advisory context.",
            len(_conflicting_lanes),
        )

    elif _strategy == "redesign":
        logger.warning(
            "DESIGN CCD-503 [redesign]: re-running design for conflicting lanes "
            "with collision details injected (%d lane(s))",
            len(_conflicting_lanes),
        )
        _apply_redesign_strategy(...)  # See below

    elif _strategy == "abort":
        logger.error(
            "DESIGN CCD-503 [abort]: marking %d conflicting lane(s) as design_failed.",
            len(_conflicting_lanes),
        )
        for _lc in _conflicting_lanes:
            for _tid in _lc.get("task_ids", []):
                design_results[_tid] = {
                    **design_results.get(_tid, {}),
                    "status": "design_failed",
                    "error": (
                        f"CCD-503 abort: design collision detected in lane "
                        f"{_lc['lane_index']} — "
                        f"{len(_lc.get('collisions', []))} conflict(s)"
                    ),
                }
```

### Redesign Strategy

A new private method `_apply_redesign_strategy()` on `DesignPhaseHandler`. Re-calls the existing design LLM path for the last task in each conflicting lane, injecting collision constraint into `additional_context`:

```python
def _apply_redesign_strategy(
    self,
    conflicting_lanes: list[dict],
    design_results: dict[str, Any],
    tasks: list[SeedTask],
    context: dict[str, Any],
    ...
) -> float:
    """Re-run design for conflicting lanes with collision context injected.

    Only the last task in each conflicting lane is redesigned.
    Returns additional cost incurred.
    """
    task_by_id = {t.task_id: t for t in tasks}
    redesign_cost = 0.0

    for lc in conflicting_lanes:
        task_ids = lc.get("task_ids", [])
        if not task_ids:
            continue
        redesign_task_id = task_ids[-1]  # last = highest wave_index
        task = task_by_id.get(redesign_task_id)
        if task is None:
            continue

        collision_text = _format_collision_context(lc.get("collisions", []))

        feature_ctx = self._task_to_feature_context(
            task,
            lane_collision_context=collision_text,  # new param
            ...
        )
        try:
            result = self._run_design_async(...)
            serialized = self._serialize_result(result)
            serialized["status"] = "redesigned"
            serialized["redesign_reason"] = "ccd_503_collision"
            design_results[redesign_task_id] = serialized
        except Exception as exc:
            logger.warning(
                "DESIGN CCD-503 [redesign]: redesign failed for task %s: %s",
                redesign_task_id, exc,
            )

    return redesign_cost
```

### Extend `_task_to_feature_context()` for Redesign Context

Add keyword-only parameter (line 1654):

```python
    lane_collision_context: str | None = None,
```

In the body, after scope_boundary injection:

```python
# CCD-503: Inject collision resolution context when redesigning
if lane_collision_context:
    additional_context["collision_resolution"] = (
        "DESIGN COLLISION ALERT: Your previous design conflicted with another "
        "task in the same lane. Please redesign with these constraints:\n"
        + lane_collision_context
    )
```

### IMPLEMENT Context Read

In `ImplementPhaseHandler.execute()` (near line 2673):

```python
# CCD-502: Read lane conflicts for advisory context injection
_lane_conflicts: list[dict[str, Any]] = context.get("lane_conflicts", [])
_conflicting_task_ids: set[str] = set()
for _lc in _lane_conflicts:
    if _lc.get("status") == "CONFLICTING":
        _conflicting_task_ids.update(_lc.get("task_ids", []))
if _conflicting_task_ids:
    logger.warning(
        "IMPLEMENT: %d task(s) in CONFLICTING design lanes: %s",
        len(_conflicting_task_ids),
        sorted(_conflicting_task_ids),
    )
```

### Tests

- `test_strategy_warn_logs_and_continues` — strategy="warn", conflicting lane → WARNING, design_results unchanged
- `test_strategy_abort_marks_tasks_as_design_failed` — strategy="abort" → all lane task IDs get `status: design_failed`
- `test_strategy_abort_preserves_other_lanes` — two lanes, one conflicting → only conflicting lane tasks failed
- `test_strategy_redesign_calls_design_again` — strategy="redesign", mock `_run_design_async` → called for redesign
- `test_strategy_default_is_warn` — `HandlerConfig()` has `design_collision_strategy="warn"`
- `test_invalid_strategy_raises` — `HandlerConfig(design_collision_strategy="magic")` → `ValueError`
- `test_lane_collision_context_injected_in_feature_context` — pass `lane_collision_context="x"`, verify key in `additional_context`

---

## Implementation Sequence

| Step | What | Files | Notes |
|---|---|---|---|
| 1 | Create `design_collision.py` with enum, dataclasses, `extract_entities()`, `_check_mode_conflicts()`, `_check_entity_collisions()`, `check_lane_collisions()` | `src/startd8/contractors/design_collision.py` | No production changes yet; write tests first |
| 2 | Add `design_collision_strategy: str = "warn"` to `HandlerConfig` with validation | `context_seed_handlers.py` | Backward-compatible default |
| 3 | Add `lane_collision_context: str | None = None` to `_task_to_feature_context()` signature + body injection | `context_seed_handlers.py` | Backward-compatible (defaults None) |
| 4 | Add post-loop collision check block between lines 2625–2627 | `context_seed_handlers.py` | Depends on Layer 1 `_design_lanes` and Layer 3 `shared_file_manifest` |
| 5 | Add resolution strategy block after collision check | `context_seed_handlers.py` | Includes `_apply_redesign_strategy()` method |
| 6 | Add `"lane_conflicts"` to `_CHECKPOINT_CONTEXT_KEYS` | `artisan_contractor.py` | Checkpoint persistence |
| 7 | Add `lane_conflicts` read + advisory log in `ImplementPhaseHandler.execute()` | `context_seed_handlers.py` | Before `_tasks_to_chunks` call |
| 8 | Write all tests | `tests/unit/contractors/test_design_collision.py` | ~35 tests |

Steps 1–3 can land in a single commit (pure additions). Steps 4–7 should land together (integrated behavior). Step 8 accompanies both commits.

---

## Context Key Convention

Following Layer 3's established pattern: no nested `context["design"]` namespace exists. Using flat keys:
- `context["lane_conflicts"]` — list of `LaneCollisionResult.to_dict()`
- `context["shared_file_manifest"]` — already established by Layer 3

---

## Test File

`tests/unit/contractors/test_design_collision.py`

Classes:
- `TestExtractEntities` (8 tests)
- `TestCheckModeConflicts` (5 tests)
- `TestCheckEntityCollisions` (4 tests)
- `TestCheckLaneCollisions` (7 tests)
- `TestLaneCollisionResultSerialization` (3 tests)
- `TestCollisionSeverityEnum` (3 tests)
- `TestResolutionStrategyIntegration` (5 tests)
- `TestHandlerConfigDesignCollisionStrategy` (3 tests)
- `TestLaneConflictContextPropagation` (3 tests)
- `TestFeatureContextCollisionInjection` (2 tests)

~35 tests total. Uses `FakeSeedTask` from `tests/unit/contractors/conftest.py`.

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Regex false positives in prose design docs | Medium | Patterns anchored at line start (`re.MULTILINE`). Entity duplicates produce `WARNING` not `CONFLICTING` — not blocking. False positives are advisory only. |
| `design_mode_summary` not yet computed when needed | Medium | Collision check placed after line 2625 where `design_mode_summary` is fully assigned. Sequencing enforced by code position. |
| Redesign adds unbounded LLM cost | Medium | `redesign` strategy only targets the last task per conflicting lane. Default is `"warn"` (zero extra cost). |
| `_design_lanes is None` when Layer 1 not yet implemented | Low | Guard `if _design_lanes is not None` wraps entire collision check. `context["lane_conflicts"] = []` always written. |
| `check_lane_collisions()` circular import risk | Low | New module imports only `startd8.logging_config`. No import from `context_seed_handlers`. SeedTask type hint uses `list` (duck-typed). |
| Collision check slows down large runs | Low | Purely algorithmic — regex on loaded text, O(L×T²) where L=lanes, T=tasks per lane. No I/O. |
| `abort` strategy and `DesignPhaseOutput` validator | Low | Aborted tasks get `status: design_failed` — same as other failed tasks. Existing validator already accepts this status. |
