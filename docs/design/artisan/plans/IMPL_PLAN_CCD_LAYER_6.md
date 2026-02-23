# Implementation Plan: Layer 6 — Contract and Telemetry (REQ-CCD-600–603)

**Status:** Ready for implementation
**Depends on:** Layers 1–5 (REQ-CCD-100–503) — specifically needs `lane_assignments`, `shared_file_manifest`, `lane_conflicts`, and per-lane `lane_index`/`lane_peer_count` data that previous layers produce
**Primary files:** `artisan-pipeline.contract.yaml`, `context_seed_handlers.py`, `artisan_contractor.py`

---

## Current State

- **`artisan-pipeline.contract.yaml`** (lines 114–150):
  - DESIGN `entry.enrichment` has two enrichment fields (`scaffold.existing_target_files` at line 125, `scaffold.staleness_classification` at line 131) and no lane-awareness fields.
  - DESIGN `exit.required` has `design_results` (line 137) with a quality gate.
  - DESIGN `exit.optional` has a single entry at line 147: `design_results.*.design_mode`. No lane metadata, no manifest fields, no lane conflict fields.
  - `schema_version` is `"0.3.0"` at line 11.
- **`_CHECKPOINT_CONTEXT_KEYS`** in `artisan_contractor.py` at lines 144–166 does not include `shared_file_manifest`, `lane_to_file_mapping`, or `lane_conflicts`.
- **DESIGN per-task span** at `context_seed_handlers.py:2336–2345`:
  - Existing attributes: `task.id`, `task.title`, `task.domain`, `task.phase`, `task.target_files`.
  - Post-task `set_attribute` calls at lines 2553–2555: `task.cost`, `task.attempts`, `task.status`.
  - No lane-awareness attributes exist.
  - `_HAS_OTEL` flag at line 120; `_phase_tracer` at line 119.
- **FINALIZE manifest** at `context_seed_handlers.py:7813–7840`:
  - Contains: `workflow_version`, `provenance`, `artifacts`, `task_status`, `summary`.
  - `summary` at lines 7916–7974 contains: `plan_title`, `task_count`, `status`, `scaffold_summary`, `implementation_summary`, `test_summary`, `review_summary`, `truncation_summary`, `gate3b_validation`, `cost_summary`, `generated_artifacts`, `artifact_count`, `dry_run`.
  - No `design_coherence` section exists.

---

## Context Key Convention

Following Layer 3's established pattern (no nested `context["design"]` namespace exists), all new context keys use flat top-level assignment:
- `context["shared_file_manifest"]` (Layer 3, REQ-CCD-301)
- `context["lane_to_file_mapping"]` (Layer 3, REQ-CCD-302)
- `context["lane_conflicts"]` (Layer 5, REQ-CCD-502)

---

## REQ-CCD-600: Contract YAML Amendment for DESIGN Phase

### Changes

**File:** `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml`

1. **Line 11** — Bump schema version from `"0.3.0"` to `"0.4.0"`.

2. **After line 135** (after `scaffold.staleness_classification` enrichment, before `exit:`): Add two new enrichment entries:
   ```yaml
       - name: lane_assignments
         type: dict
         severity: advisory
         description: "Per-task lane assignments from compute_lanes(). Advisory — DESIGN falls back to flat iteration if absent."
       - name: wave_assignments
         type: dict
         severity: advisory
         description: "Per-task wave indices for lane-internal ordering (from plan phase wave_assignments)."
   ```

3. **After line 150** (after existing `design_results.*.design_mode` optional entry): Add four new optional exit fields:
   ```yaml
       - name: design_results.*.lane_index
         type: int
         description: "Lane index assigned to this task during DESIGN. Matches IMPLEMENT lane computation. 0 when lane computation fell back."
       - name: design_results.*.wave_index
         type: int
         description: "Wave index used for lane-internal ordering. null when not available."
       - name: shared_file_manifest
         type: dict
         description: "Per-file map of contesting task IDs. Empty dict if no shared files. Set by REQ-CCD-300."
       - name: lane_conflicts
         type: list
         description: "Post-lane compatibility check results from REQ-CCD-500. Empty list if no conflicts detected or lane computation fell back."
   ```

### Notes on `severity: advisory`

All four new optional fields carry advisory severity because the DESIGN phase operates correctly without them (REQ-CCD-104 fallback). The `gate_contracts.py` validator treats `advisory` fields as informational — missing values emit no warnings.

### Tests

- `test_design_entry_enrichment_has_lane_assignments` — load contract YAML, verify entry present with `severity: advisory`
- `test_design_entry_enrichment_has_wave_assignments` — verify entry present
- `test_design_exit_optional_has_lane_index` — verify `design_results.*.lane_index` in optional section
- `test_design_exit_optional_has_shared_file_manifest` — verify `shared_file_manifest`
- `test_design_exit_optional_has_lane_conflicts` — verify `lane_conflicts`
- `test_schema_version_bumped` — verify `schema_version` is `"0.4.0"`
- `test_existing_required_fields_unchanged` — regression guard
- `test_existing_optional_design_mode_unchanged` — regression guard

---

## REQ-CCD-601: OTel Span Attributes for Lane Context

### Changes

**File:** `context_seed_handlers.py`

1. **Lines 2336–2345** — Extend the span's initial `attributes` dict:
   ```python
   _task_span_cm = _phase_tracer.start_as_current_span(
       f"task.{task.task_id}",
       attributes={
           "task.id": task.task_id,
           "task.title": task.title,
           "task.domain": task.domain or "",
           "task.phase": "design",
           "task.target_files": ",".join(task.target_files[:5]),
           # CCD-601: lane-awareness attributes
           "task.lane_index": _lane_assignments.get(task.task_id, 0),
           "task.lane_peer_count": (
               len(_design_lanes[_lane_assignments[task.task_id]]) - 1
               if _design_lanes and task.task_id in _lane_assignments
               else -1  # sentinel: lane computation not performed
           ),
           "task.shared_file_count": sum(
               1 for tf in task.target_files
               if _normalize_target_path(tf) in shared_file_manifest
           ) if shared_file_manifest else 0,
       },
   )
   ```

   **Implementation notes:**
   - `_lane_assignments` from Layer 1 (REQ-CCD-100). Fallback: `{}`, so `.get(task.task_id, 0)` returns 0.
   - `task.lane_peer_count = -1` is the sentinel for "lane computation not performed" (CCD-104 fallback).
   - `task.shared_file_count` uses `_normalize_target_path()` from Layer 3 for consistent path comparison.
   - Set at span creation so present even if the task errors out.

2. **After line 2555** (success branch, after `task.status = "designed"`):
   ```python
   # CCD-601: lane-peer context injection attributes
   _lane_prior_count = len(lane_prior_designs) if lane_prior_designs else 0
   _lane_prior_truncated = False  # set by budget guard if CCD-203 lands
   _task_span.set_attribute("task.lane_prior_designs_count", _lane_prior_count)
   _task_span.set_attribute("task.lane_prior_designs_truncated", _lane_prior_truncated)
   ```

   **Note:** `lane_prior_designs` is Layer 2 (REQ-CCD-200). `_lane_prior_truncated` from CCD-203 budget guard; defaults `False` until that lands.

3. **After per-lane collision check** (Layer 5) — set collision severity attribute:
   ```python
   # CCD-601: collision severity from post-lane check
   _lane_conflict_status = _get_lane_conflict_status(
       _lane_assignments.get(task.task_id, 0),
       lane_conflicts,
   )
   if _lane_conflict_status:
       _task_span.set_attribute("design.collision_severity", _lane_conflict_status)
   ```

### Defensive Constant

Add near line 125 alongside other module-level constants:
```python
# CCD-601/602: Canonical attribute names for design-phase lane-awareness.
# Changing these names breaks dashboard queries documented in
# docs/design/artisan/plans/CCD_LAYER6_TEMPO_QUERIES.md
_CCD_DESIGN_SPAN_ATTRS = frozenset({
    "task.lane_index",
    "task.lane_peer_count",
    "task.shared_file_count",
    "task.lane_prior_designs_count",
    "task.lane_prior_designs_truncated",
    "design.collision_severity",
})
```

### Tests

- `test_lane_index_attr_on_span_creation` — mock span capture, verify `task.lane_index` set
- `test_lane_peer_count_negative_one_when_fallback` — `_design_lanes=None`, verify `-1`
- `test_lane_peer_count_zero_for_single_task_lane` — 1 task in lane, verify `0`
- `test_shared_file_count_attr` — task with 2 contested files, verify `2`
- `test_shared_file_count_zero_when_manifest_empty` — `shared_file_manifest={}`, verify `0`
- `test_lane_prior_designs_count_attr` — after designed branch, verify attribute set
- `test_lane_prior_designs_truncated_default_false` — verify default before budget guard lands
- `test_collision_severity_attr_set` — when lane_conflicts populated, verify `design.collision_severity`
- `test_span_attrs_present_on_adopted_path` — adopted path still gets lane_index and shared_file_count
- `test_ccd_span_attrs_constant_covers_all_traceql_attributes` — programmatic check

---

## REQ-CCD-602: Grafana Dashboard Queries

### Changes

**This requirement produces no production code changes.** The TraceQL queries are validated against the span schema from REQ-CCD-601.

**Documentation file:** `docs/design/artisan/plans/CCD_LAYER6_TEMPO_QUERIES.md`

#### Query 1: Tasks Designed with Lane-Peer Context
```
{ span.task.lane_peer_count > 0 }
```
Returns all task spans where lane-peer context was injected. Measures CCD adoption.

#### Query 2: Shared-File Tasks Without Peer Context (Design Isolation)
```
{ span.task.shared_file_count > 0 && span.task.lane_prior_designs_count = 0 }
```
Pre-CCD baseline: tasks that contested shared files but received no lane-peer context. After CCD lands, should be empty (except first-in-lane tasks).

#### Query 3: Token Budget Truncation Events
```
{ span.task.lane_prior_designs_truncated = true }
```
Tasks where CCD-203 token budget guard truncated lane-peer context.

#### Query 4: Design Collision Events by Severity
```
{ span.design.collision_severity = "CONFLICTING" }
```
Tasks in lanes with definite design conflicts. Actionable for `redesign`/`abort` strategy tuning.

#### Query 5: Lane-Aware vs Flat Iteration Ratio
```
{ span.task.phase = "design" && span.task.lane_index >= 0 }
```
Compare with `{ span.task.lane_peer_count = -1 }` for fallback proportion.

### Tests

- `test_traceql_queries_are_documented` — verify `CCD_LAYER6_TEMPO_QUERIES.md` exists and contains the 5 queries
- `test_span_attribute_names_match_queries` — extract attribute names from queries, verify each in `_CCD_DESIGN_SPAN_ATTRS`

---

## REQ-CCD-603: Lane Coherence Status in FINALIZE Manifest

### Changes

**File:** `context_seed_handlers.py`

1. **New static method on `FinalizePhaseHandler`** (after `_count_gate3b_by_severity` at ~line 7868):
   ```python
   @staticmethod
   def _build_design_coherence_summary(context: dict[str, Any]) -> dict[str, Any]:
       """Build design coherence summary for generation-manifest.json.

       Consumes lane_conflicts (REQ-CCD-502), lane_to_file_mapping (REQ-CCD-302),
       and shared_file_manifest (REQ-CCD-301) from context.
       """
       lane_conflicts: list[dict[str, Any]] = context.get("lane_conflicts", [])
       lane_to_file_mapping: dict[int, list[str]] = context.get("lane_to_file_mapping", {})
       shared_file_manifest: dict[str, list[str]] = context.get("shared_file_manifest", {})

       # Sentinel: lane computation was not performed
       if context.get("_design_lane_computation_skipped", False):
           return {
               "status": "NOT_COMPUTED",
               "reason": "lane computation fell back to flat iteration",
           }

       total_lanes = context.get("_design_lane_count", 0)
       shared_file_lanes = len(lane_to_file_mapping)

       coherent_lanes = sum(
           1 for lc in lane_conflicts if lc.get("status") == "COHERENT"
       )
       warning_lanes = sum(
           1 for lc in lane_conflicts if lc.get("status") == "WARNING"
       )
       conflicting_lanes = sum(
           1 for lc in lane_conflicts if lc.get("status") == "CONFLICTING"
       )
       shared_file_count = len(shared_file_manifest)

       lane_details: list[dict[str, Any]] = []
       for lc in lane_conflicts:
           lane_idx = lc.get("lane_index")
           if lane_idx is None:
               continue
           shared_files = lane_to_file_mapping.get(lane_idx, [])
           lane_details.append({
               "lane_index": lane_idx,
               "task_ids": lc.get("task_ids", []),
               "shared_files": shared_files,
               "status": lc.get("status", "COHERENT"),
           })

       return {
           "total_lanes": total_lanes,
           "shared_file_lanes": shared_file_lanes,
           "coherent_lanes": coherent_lanes,
           "warning_lanes": warning_lanes,
           "conflicting_lanes": conflicting_lanes,
           "shared_file_count": shared_file_count,
           "lane_details": lane_details,
       }
   ```

2. **In `execute()`** — after line 7969 (`"gate3b_validation": {}`):
   ```python
   # CCD-603: Design coherence summary
   summary["design_coherence"] = self._build_design_coherence_summary(context)
   ```

3. **In `_write_manifest()`** — add `design_coherence` at manifest root level:
   ```python
   manifest = {
       "workflow_version": "0.4.0",
       "provenance": { ... },
       "artifacts": artifacts,
       "task_status": task_status,
       "summary": { ... },
       "design_coherence": summary.get("design_coherence", {"status": "NOT_COMPUTED"}),
   }
   ```

4. **Context flags** — In Layer 1's DESIGN handler (CCD-104 fallback path), set:
   ```python
   context["_design_lane_computation_skipped"] = _design_lanes is None
   context["_design_lane_count"] = len(_design_lanes) if _design_lanes else 0
   ```

5. **`_CHECKPOINT_CONTEXT_KEYS` in `artisan_contractor.py`** (line 144) — Add five new keys:
   ```python
   "shared_file_manifest",
   "lane_to_file_mapping",
   "lane_conflicts",
   "_design_lane_computation_skipped",
   "_design_lane_count",
   ```

### Tests

- `test_design_coherence_in_manifest` — FINALIZE with mock lane data, verify `design_coherence` key
- `test_design_coherence_counts_correct` — 3 lanes (1 coherent, 1 warning, 1 conflicting), verify counts
- `test_design_coherence_not_computed_sentinel` — `_design_lane_computation_skipped=True`, verify sentinel
- `test_design_coherence_empty_default` — no lane data (pre-CCD), verify graceful defaults
- `test_lane_details_populated` — verify `lane_details` entries match expected structure
- `test_design_coherence_in_manifest_root` — verify at manifest root (not just summary)
- `test_checkpoint_keys_include_ccd_fields` — verify all 5 new keys in `_CHECKPOINT_CONTEXT_KEYS`
- `test_build_design_coherence_summary_no_conflict_data` — `lane_conflicts=[]`, verify zero counts

---

## Implementation Sequence

| Step | Action | Requirement | Notes |
|------|--------|-------------|-------|
| 1 | Bump `schema_version` to `"0.4.0"` + add DESIGN entry enrichment fields | REQ-CCD-600 | Pure YAML; no code impact |
| 2 | Add optional exit fields to DESIGN contract | REQ-CCD-600 | Same file, same commit |
| 3 | Add `_CCD_DESIGN_SPAN_ATTRS` constant | REQ-CCD-602 | Establishes stable attribute name contract |
| 4 | Extend DESIGN per-task span attributes (creation-time) | REQ-CCD-601 | Depends on Layer 1 + Layer 3 |
| 5 | Add `task.lane_prior_designs_count` + `task.lane_prior_designs_truncated` | REQ-CCD-601 | Depends on Layer 2 |
| 6 | Add `design.collision_severity` attribute | REQ-CCD-601 | Depends on Layer 5 |
| 7 | Set `_design_lane_computation_skipped` + `_design_lane_count` context flags | REQ-CCD-603 (setup) | Two-line addition to CCD-100/104 block |
| 8 | Add `_build_design_coherence_summary()` to `FinalizePhaseHandler` | REQ-CCD-603 | Pure computation |
| 9 | Inject `design_coherence` into `summary` and `manifest` | REQ-CCD-603 | Two insertion points |
| 10 | Add 5 new keys to `_CHECKPOINT_CONTEXT_KEYS` | REQ-CCD-603 | Resume correctness |
| 11 | Create `CCD_LAYER6_TEMPO_QUERIES.md` | REQ-CCD-602 | Documentation |

**Steps 1–2 can land in isolation.** Steps 3–6 depend on Layers 1–5 but can use empty-state defaults via `.get()` with fallbacks. Steps 8–9 are standalone. Step 10 is backward-compatible.

---

## Consolidated Change Summary

| File | Location | Lines Affected | Change |
|------|----------|---------------|--------|
| `artisan-pipeline.contract.yaml` | Line 11 | 1 | Bump schema_version `"0.3.0"` → `"0.4.0"` |
| `artisan-pipeline.contract.yaml` | After line 135 | +10 lines | Two new entry enrichment fields |
| `artisan-pipeline.contract.yaml` | After line 150 | +16 lines | Four new optional exit fields |
| `context_seed_handlers.py` | ~line 125 | +5 lines | `_CCD_DESIGN_SPAN_ATTRS` frozenset constant |
| `context_seed_handlers.py` | Lines 2336–2345 | +5 lines | Three new span creation attributes |
| `context_seed_handlers.py` | ~line 2555 | +4 lines | Two post-task span attributes |
| `context_seed_handlers.py` | ~line 2590 | +4 lines | `design.collision_severity` attribute |
| `context_seed_handlers.py` | ~line 2056 (Layer 1 block) | +2 lines | Lane computation state flags |
| `context_seed_handlers.py` | ~line 7595 | +45 lines | `_build_design_coherence_summary()` method |
| `context_seed_handlers.py` | ~line 7969 | +3 lines | `summary["design_coherence"]` injection |
| `context_seed_handlers.py` | ~line 7830 | +2 lines | `"design_coherence"` in manifest root |
| `artisan_contractor.py` | Lines 144–166 | +5 lines | Five new `_CHECKPOINT_CONTEXT_KEYS` entries |

**Two production files, ~100 lines total. No new modules required.**

---

## Test File

`tests/unit/contractors/test_ccd_layer6_contract_telemetry.py`

Classes:
- `TestContractYAMLAmendment` (10 tests)
- `TestDesignPhaseSpanAttributes` (11 tests)
- `TestTraceQLQueryDocumentation` (3 tests)
- `TestDesignCoherenceSummary` (8 tests)
- `TestCheckpointKeysInclusion` (5 tests)

~35 tests total. Uses `FakeSeedTask` from `conftest.py`, existing `_NoOpTracer`/`_NoOpSpan` mocks for span capture.

---

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Layer 1–5 not yet landed when Layer 6 ships | Low | All span attribute reads use `.get(key, default)`. Zero-value attributes emitted, enabling pre-CCD baseline queries. |
| `_design_lane_computation_skipped` flag not set when Layer 1 not present | Low | `_build_design_coherence_summary()` defaults to `context.get("_design_lane_computation_skipped", False)` — when False and lane data absent, emits zero counts (safe degraded state). |
| `manifest["design_coherence"]` breaks downstream manifest consumers | None | Manifest schema is not versioned by external tools; adding a new top-level key is additive. |
| `schema_version` bump triggers `gate_contracts.py` validation failure | Low | Check validator's version parsing — if strict equality, update needed; current YAML loader does not enforce at runtime. |
| `_CHECKPOINT_CONTEXT_KEYS` additions break existing checkpoint files | None | Keys read via `context.get(key)` — old checkpoints without keys silently return `None`. |
| `task.lane_peer_count = -1` sentinel is ambiguous in Tempo queries | Low | Documented in `CCD_LAYER6_TEMPO_QUERIES.md`. Filter with `> -1` to exclude fallback runs. |
