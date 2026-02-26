# Phase 4 Extension: Artisan IMPLEMENT Phase Forward Manifest Injection

**Version:** 1.0.0
**Created:** 2026-02-26
**Status:** Implemented
**Extends:** [06_PHASE4_THREADING_PLAN.md](06_PHASE4_THREADING_PLAN.md)
**Context:** Phase 4 originally wired the `ForwardManifest` into the Artisan `DESIGN` phase via `ContractModule` (confirmed working). This document captures the gap discovery and subsequent implementation that extended contract injection into the `IMPLEMENT` phase, closing the loop on full artisan pipeline enforcement.

---

## 1. Problem Statement

Despite the `ForwardManifest` being correctly rendered in `DESIGN` phase prompts, the `IMPLEMENT` phase had zero awareness of interface contracts. This was confirmed by inspecting walkthrough prompt exports in `.startd8/walkthrough/implement/PI-003/t1_user_prompt.md` — **no forward manifest content was present**.

As a result, code generation during `IMPLEMENT` proceeded without the interface bindings (e.g., required class hierarchies, function signatures) that were specified for that task. The LLM had no structural anchor to prevent hallucinations or missing inheritance.

---

## 2. Root Cause

The `ImplementPhaseHandler._tasks_to_chunks()` method in `context_seed_handlers.py` builds `DevelopmentChunk` metadata that is later used to assemble the IMPLEMENT prompt. It accepted many context parameters but did **not** include `forward_manifest` — it was never passed in, and the chunk builder had no logic to call `map_forward_contracts_for_task`.

Although `context["forward_manifest"]` was available in the shared context (set by `PlanPhaseHandler` after ingestion), `_tasks_to_chunks` never read it and the prompt builder in `development.py` had no corresponding helper to render it.

---

## 3. Requirements

### 3.1 Forward Manifest Available in Shared Context (REQ-IMP-FM-001)

**Requirement:** `context["forward_manifest"]` must be populated before `ImplementPhaseHandler.execute()` is called.

**Status:** ✅ Already satisfied — `PlanPhaseHandler` loads and stores the hydrated `ForwardManifest` into `context["forward_manifest"]` at PLAN phase exit.

---

### 3.2 Pass Forward Manifest to `_tasks_to_chunks` (REQ-IMP-FM-002)

**Requirement:** `ImplementPhaseHandler.execute()` must thread `forward_manifest` from `context` into `_tasks_to_chunks()`.

**Implementation:**

- `_tasks_to_chunks` signature updated to accept `**kwargs: Any` to avoid a massive signature expansion.
- `execute()` passes `forward_manifest=context.get("forward_manifest")` in the call at line ~6622 of `context_seed_handlers.py`.

**Status:** ✅ Implemented

---

### 3.3 Extract Interface Contracts per Task (REQ-IMP-FM-003)

**Requirement:** For each `SeedTask`, extract applicable Forward Manifest contracts using `map_forward_contracts_for_task`, then render them via `ContractModule` into a formatted prompt string.

**Implementation:**

- Inside the `for task in tasks:` loop in `_tasks_to_chunks`, retrieve `forward_manifest = kwargs.get("forward_manifest")`.
- If present, call `map_forward_contracts_for_task(task, forward_manifest=forward_manifest)`.
- If contracts are found, call `ContractModule().render(contract_data)` to produce the formatted text fragment.
- Store the result as `_forward_contracts` (a `str | None`).

**Status:** ✅ Implemented

---

### 3.4 Inject Contracts into DevelopmentChunk Metadata (REQ-IMP-FM-004)

**Requirement:** The rendered contracts string must be stored in `chunk.metadata["forward_contracts"]` for each `DevelopmentChunk`.

**Implementation:**

- Added `"forward_contracts": _forward_contracts` to the `metadata` dict in `DevelopmentChunk(...)` construction.

**Status:** ✅ Implemented

---

### 3.5 Render Contracts in IMPLEMENT Prompt (REQ-IMP-FM-005)

**Requirement:** The IMPLEMENT prompt builder must read `chunk.metadata["forward_contracts"]` and surface it as a named section in the user prompt.

**Implementation:**

- Added `_build_forward_contracts(chunk)` static method to `ArtisanChunkExecutor` (in `development.py`).
- Inserted the call at the correct location in `_build_task_description()`, **after** `_build_manifest_context` (Phase 4) and **before** `_build_call_graph_context` (Phase 6), so contracts appear alongside structural context.
- When `forward_contracts` in metadata is `None` or empty, the method returns `[]` (no-op).

**Status:** ✅ Implemented

---

### 3.6 Backward Compatibility (REQ-IMP-FM-006)

**Requirement:** When `forward_manifest` is absent in the context, all new code paths must degrade gracefully with no error.

**Implementation:**

- `_tasks_to_chunks` checks `if forward_manifest is not None` before invoking extractor/module.
- `_build_forward_contracts` returns `[]` when metadata key is absent.
- No change in behavior for seeds without a `forward_manifest`.

**Status:** ✅ Implemented

---

## 4. Files Modified

| File | Change |
|------|--------|
| `src/startd8/contractors/context_seed_handlers.py` | `_tasks_to_chunks`: Added `**kwargs` to signature; added Phase 5 Forward Manifest contract extraction loop; added `"forward_contracts"` to chunk metadata. `execute()`: Added `forward_manifest=context.get("forward_manifest")` to `_tasks_to_chunks` call. |
| `src/startd8/contractors/artisan_phases/development.py` | Added `_build_forward_contracts()` static helper to `ArtisanChunkExecutor`; added `_build_forward_contracts` call to `_build_task_description()` ordering. |

---

## 5. Verification Plan

### 5.1 Walkthrough Prompt Inspection

Run the Artisan workflow with `--walkthrough` on a seed that contains `forward_manifest` contracts:

```bash
.cap-dev-pipe/run-artisan.sh --seed .startd8/enriched-context-seed.json \
  --walkthrough --task-filter PI-003
```

Inspect `.startd8/walkthrough/implement/PI-003/t1_user_prompt.md` and assert:

- A new section (rendered by `ContractModule`) appears under the Target Files / Manifest Context blocks.
- The section contains binding constraint text (e.g., `[BINDING] function=...` or class hierarchy requirements).

### 5.2 Code Compliance Check

Run a full IMPLEMENT pipeline on a plan that specifies a required interface (e.g., a base class `IRecommendationService`). After generation:

- Confirm the generated source file contains `class RecommendationService(IRecommendationService)` (or equivalent).
- Previously this was absent, indicating the LLM did not know about the contract.

### 5.3 Regression: Manifest Absent

Run with a seed that has no `forward_manifest` key. Assert:

- No `KeyError`, `AttributeError` or crash.
- Prompt output is identical to pre-change behavior (no phantom sections).

---

## 6. Relation to Other Phase 4 Requirements

This document closes the gap left open in `06_PHASE4_THREADING_PLAN.md` Section 3.3 ("Remaining: IMPLEMENT Pipeline Integration"). The DESIGN phase wire-up described in the base threading plan was already completed prior to this session. The present work is the IMPLEMENT counterpart.

See also:

- [04_FORWARD_MANIFEST.md](04_FORWARD_MANIFEST.md) — Core schema definition
- [06_PHASE4_THREADING_PLAN.md](06_PHASE4_THREADING_PLAN.md) — Phase 4 threading strategy (DESIGN wire-up)
- [05_PHASE5_VALIDATOR_REQUIREMENTS.md](05_PHASE5_VALIDATOR_REQUIREMENTS.md) — Post-generation validator (REVIEW phase)
