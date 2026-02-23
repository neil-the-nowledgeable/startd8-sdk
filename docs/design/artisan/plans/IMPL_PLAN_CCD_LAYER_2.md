# Implementation Plan: Layer 2 — Cumulative Design Context (REQ-CCD-200–205)

**Status:** Ready for implementation
**Depends on:** Layer 1 (REQ-CCD-100–104)
**Primary file:** `src/startd8/contractors/context_seed_handlers.py`

---

## Current State

- `prior_summaries: list[str]` at line 2209 — accumulates 300-char first-line truncations
- Accumulation at lines 2407-2411 (adopted) and 2537-2541 (fresh): `doc_text[:300].split("\n")[0]`
- `_task_to_feature_context()` at line 1635 — `@staticmethod`, 20 keyword-only params, returns `FeatureContext`
- `additional_context["prior_designs"]` at lines 1729-1733 — last 5 summaries injected
- Call site at line 2468 — passes `prior_design_summaries=prior_summaries`
- `FeatureContext.additional_context` is `dict[str, Any]` — rendered into prompt by `design_documentation.py` line ~1166

---

## REQ-CCD-200: Full Design Documents for Lane Peers

### Changes

**File:** `context_seed_handlers.py`

1. **Line ~2209** — Add accumulator alongside `prior_summaries`:
   ```python
   prior_summaries: list[str] = []
   lane_prior_designs: list[dict[str, Any]] = []
   ```

2. **Lane reset** — At the start of each lane in the `_iteration_order` construction (Layer 1), reset:
   ```python
   # At start of each lane's tasks in _iteration_order:
   lane_prior_designs = []
   ```

3. **Lines 2407-2411** (adopted path) — Add parallel accumulation:
   ```python
   lane_prior_designs.append({
       "task_id": task.task_id,
       "title": task.title,
       "design_document": doc_text,
   })
   ```

4. **Lines 2537-2541** (fresh design path) — Same parallel accumulation with `result.design_document.raw_text`

### Tests
- `test_lane_prior_designs_accumulates` — 3 tasks in same lane, verify list grows with full docs
- `test_lane_prior_designs_resets_per_lane` — 2 lanes, verify reset at lane boundary
- `test_adopted_design_added` — adopted path adds full doc text
- `test_prior_summaries_still_populated` — existing cross-lane summaries unchanged

---

## REQ-CCD-201: Two-Tier Context Model

### Changes

**File:** `context_seed_handlers.py` — replace lines 1729-1733:

```python
# Tier 1: Lane-peer designs (full documents)
if lane_prior_designs:
    additional_context["lane_peer_designs"] = _format_lane_peer_context(
        lane_prior_designs, shared_file_manifest, task,
    )

# Tier 2: Cross-lane summaries (exclude lane peers to avoid duplication)
if prior_design_summaries:
    lane_peer_ids = {d["task_id"] for d in (lane_prior_designs or [])}
    cross_lane = [
        s for s in prior_design_summaries
        if not any(s.startswith(f"{pid} (") for pid in lane_peer_ids)
    ]
    if cross_lane:
        additional_context["prior_designs"] = (
            "Previously designed tasks (other lanes):\n"
            + "\n".join(f"- {s}" for s in cross_lane[-5:])
        )
```

**Deduplication note:** Filter uses `f"{pid} ("` prefix match (not bare `pid`) to avoid false matches when task IDs are prefixes of each other (e.g., `PI-1` vs `PI-10`).

### Tests
- `test_two_tier_lane_peer_in_context` — verify `lane_peer_designs` key with full docs
- `test_two_tier_excludes_lane_peers_from_summaries` — verify `prior_designs` excludes same-lane tasks
- `test_backward_compat_no_lane_context` — `lane_prior_designs=None` produces identical old behavior

---

## REQ-CCD-202: Design Prompt Injection Format

### Changes

**New helper function** (~line 1600):

```python
def _format_lane_peer_context(
    lane_prior_designs: list[dict[str, Any]],
    shared_file_manifest: dict[str, list[str]] | None,
    current_task: SeedTask,
) -> str:
    """Format lane-peer designs with compatibility instruction and shared-file annotations."""
```

Produces structured output:
```
=== LANE-PEER DESIGN CONTEXT ===
The following tasks share files with this task. Your design MUST be compatible...

--- Peer: PI-001 (Add health check) ---
  Shared files: src/utils.py, src/config.py
[full design document text]
--- End: PI-001 ---

=== END LANE-PEER DESIGN CONTEXT ===
```

### Tests
- `test_format_structure` — verify delimiters and instruction header
- `test_shared_files_annotated` — verify per-peer shared file listing
- `test_empty_returns_empty_string` — empty input → ""

---

## REQ-CCD-203: Token Budget Guard

### Changes

1. **HandlerConfig** (~line 431) — Add: `design_lane_peer_token_budget: int = 8000`

2. **New helper** (~line 1600):
   ```python
   def _apply_lane_peer_token_budget(
       lane_prior_designs: list[dict[str, Any]],
       budget_tokens: int,
   ) -> tuple[list[dict[str, Any]], bool]:
   ```

3. **Algorithm:** Estimate tokens via `chars / 4`. When over budget, truncate oldest peers to 300-char summaries (most recent keeps full doc). Log WARNING when truncation occurs.

4. **Integration:** Call before `_format_lane_peer_context()` in `_task_to_feature_context()`.

### Tests
- `test_budget_no_truncation_under_limit` — small docs, budget 8000
- `test_budget_truncates_oldest_first` — 4 large docs, oldest truncated
- `test_single_peer_never_truncated` — 1 peer over budget, kept as-is

---

## REQ-CCD-204: Extend `_task_to_feature_context()` Signature

### Changes

**File:** `context_seed_handlers.py` — line 1635, add after `scaffold_existing_files`:

```python
    lane_prior_designs: list[dict[str, Any]] | None = None,
    shared_file_manifest: dict[str, list[str]] | None = None,
    wave_index: int | None = None,
    lane_peer_token_budget: int = 8000,
```

**Call site** (line ~2468) — pass new parameters:
```python
    lane_prior_designs=lane_prior_designs,
    shared_file_manifest=shared_file_manifest,
    wave_index=task.wave_index,
    lane_peer_token_budget=self.config.design_lane_peer_token_budget,
```

All new params default to `None`/`8000` — backward compatible with all existing call sites.

### Tests
- `test_signature_backward_compatible` — call with only `task` param, no error
- `test_lane_prior_designs_flows_to_additional_context` — pass designs, verify key present

---

## REQ-CCD-205: Lane-Peer Design Accumulation

### Changes

Same code paths as REQ-CCD-200 — the accumulation logic at lines 2407-2411 and 2537-2541. Both `prior_summaries.append()` and `lane_prior_designs.append()` happen in parallel.

**Key constraint:** `prior_summaries` continues to be populated for ALL tasks (including lane peers) for backward-compatible cross-lane context. Deduplication happens in `_task_to_feature_context()` (REQ-CCD-201), not at accumulation time.

### Tests
- `test_accumulation_parallel` — both accumulators grow in lockstep
- `test_failed_task_not_accumulated` — exception path does not append to `lane_prior_designs`

---

## Implementation Order

1. REQ-CCD-204 (signature change — enables all others, no behavioral change)
2. REQ-CCD-200 + REQ-CCD-205 (accumulator + accumulation — same code paths)
3. REQ-CCD-203 (token budget — must land before CCD-201 to prevent prompt explosion)
4. REQ-CCD-201 (two-tier context model)
5. REQ-CCD-202 (prompt formatting)

CCD-200, 203, 204, 205 should land in a single commit. CCD-201 and 202 can follow.

---

## Test File

`tests/unit/contractors/test_ccd_layer2_cumulative_context.py`

Classes: `TestLanePriorDesignsAccumulator`, `TestTwoTierContextModel`, `TestLanePeerPromptFormat`, `TestLanePeerTokenBudget`, `TestTaskToFeatureContextSignature`

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Prompt size explosion without budget | Medium | CCD-203 must land alongside CCD-200 |
| Memory (full docs in list) | Low | ~2-5KB per doc × 20 tasks = 40-100KB |
| Filtering prefix collision | Low | Use `f"{pid} ("` pattern, not bare `pid` |
