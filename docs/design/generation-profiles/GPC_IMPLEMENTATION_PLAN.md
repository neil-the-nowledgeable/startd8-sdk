# Implementation Plan: Generation Profile Consumer Integration (REQ-GPC)

**Status:** Draft
**Date:** 2026-03-16
**Requirements:** [REQ-GPC_GENERATION_PROFILE_CONSUMER.md](REQ-GPC_GENERATION_PROFILE_CONSUMER.md)

---

## Overview

~100 lines across 10 files in 4 phases. Phase A is the critical path — prevents all silent data poisoning from ContextCore profile-omitted markers.

---

## Phase A: Foundation (must ship together)

### Step A1: Create `seeds/utils.py` (REQ-GPC-100)

**New file:** `src/startd8/seeds/utils.py`

```python
"""Shared seed utilities."""

from __future__ import annotations

from typing import Any

__all__ = ["is_omitted"]


def is_omitted(value: Any) -> bool:
    """Return True if value is a ContextCore profile-omitted marker.

    ContextCore replaces omitted onboarding sections with
    ``{"_omitted": "profile=<name>"}`` under non-full profiles.
    """
    return isinstance(value, dict) and "_omitted" in value
```

**Tests:** `tests/unit/seeds/test_utils.py`
- `test_is_omitted_detects_markers` — `{"_omitted": "profile=source"}` → `True`
- `test_is_omitted_rejects_normal_dicts` — `{"dashboard": {...}}` → `False`
- `test_is_omitted_handles_none_and_list` — `None`, `[]`, `""`, `42` → `False`

---

### Step A2: Extract `generation_profile` at PLAN phase (REQ-GPC-200)

**File:** `src/startd8/contractors/context_seed/phases/plan.py`

**After line 135** (`_onboarding = seed_data.get("onboarding") or {}`), add:

```python
        # REQ-GPC-200: extract generation profile for downstream profile-awareness
        context["generation_profile"] = _onboarding.get("generation_profile", "full")
```

**Verification:** This is a single assignment, placed immediately after `_onboarding` is populated and before the 8-field extraction loop.

---

### Step A3: Guard extraction loop against omitted markers (REQ-GPC-201)

**File:** `src/startd8/contractors/context_seed/phases/plan.py`

**Change lines 136-157** — the 8-field extraction loop. Replace direct `.get()` assignments with `is_omitted()` guards:

**Before (lines 136-152):**
```python
        context["onboarding_derivation_rules"] = _onboarding.get("derivation_rules")
        context["onboarding_resolved_parameters"] = _onboarding.get(
            "resolved_artifact_parameters"
        )
        context["onboarding_output_contracts"] = _onboarding.get(
            "expected_output_contracts"
        )
        context["onboarding_calibration_hints"] = _onboarding.get(
            "design_calibration_hints"
        )
        context["onboarding_open_questions"] = _onboarding.get("open_questions")
        context["onboarding_dependency_graph"] = _onboarding.get(
            "artifact_dependency_graph"
        )
        context["service_metadata"] = _onboarding.get("service_metadata")
        context["onboarding_schema_features"] = (
            _onboarding.get("capabilities", {}).get("schema_features")
            or _onboarding.get("schema_features")
        )
```

**After:**
```python
        from startd8.seeds.utils import is_omitted

        # REQ-GPC-201: skip omitted markers → None activates fallback heuristics
        _raw_dr = _onboarding.get("derivation_rules")
        context["onboarding_derivation_rules"] = None if is_omitted(_raw_dr) else _raw_dr
        _raw_rp = _onboarding.get("resolved_artifact_parameters")
        context["onboarding_resolved_parameters"] = None if is_omitted(_raw_rp) else _raw_rp
        _raw_oc = _onboarding.get("expected_output_contracts")
        context["onboarding_output_contracts"] = None if is_omitted(_raw_oc) else _raw_oc
        _raw_ch = _onboarding.get("design_calibration_hints")
        context["onboarding_calibration_hints"] = None if is_omitted(_raw_ch) else _raw_ch
        _raw_oq = _onboarding.get("open_questions")
        context["onboarding_open_questions"] = None if is_omitted(_raw_oq) else _raw_oq
        _raw_dg = _onboarding.get("artifact_dependency_graph")
        context["onboarding_dependency_graph"] = None if is_omitted(_raw_dg) else _raw_dg
        _raw_sm = _onboarding.get("service_metadata")
        context["service_metadata"] = None if is_omitted(_raw_sm) else _raw_sm
        _raw_sf = (
            _onboarding.get("capabilities", {}).get("schema_features")
            or _onboarding.get("schema_features")
        )
        context["onboarding_schema_features"] = None if is_omitted(_raw_sf) else _raw_sf
```

**Note:** The `_fwd_count` summary (lines 158-170) counts non-falsy values, so `None` from omitted fields won't be counted — no change needed there.

**Tests:** `tests/unit/contractors/context_seed/test_plan_phase_gpc.py`
- `test_plan_phase_sets_omitted_fields_to_none` — Seed with 5 `_omitted` markers → all 5 context keys are `None`
- `test_plan_phase_preserves_non_omitted_fields` — Normal dict values pass through unchanged
- `test_plan_phase_extracts_generation_profile` — `"source"` from onboarding
- `test_plan_phase_defaults_to_full` — Missing field → `"full"`

---

### Step A4: Restore `generation_profile` on resume (REQ-GPC-202)

**File:** `src/startd8/contractors/context_seed/shared.py`

**In `_ensure_context_loaded()`, after line 384** (`_onboarding = seed_data.get("onboarding") or {}`), add:

```python
    # REQ-GPC-202: restore generation profile on resume
    if "generation_profile" not in context:
        context["generation_profile"] = _onboarding.get("generation_profile", "full")
```

**Also in the PCA-201 re-extraction block (lines 385-404)**, apply `is_omitted()` guards to the `_pca_fields` dict:

**Before (lines 385-397):**
```python
    _pca_fields = {
        "onboarding_derivation_rules": _onboarding.get("derivation_rules"),
        "onboarding_resolved_parameters": _onboarding.get("resolved_artifact_parameters"),
        "onboarding_output_contracts": _onboarding.get("expected_output_contracts"),
        "onboarding_calibration_hints": _onboarding.get("design_calibration_hints"),
        "onboarding_open_questions": _onboarding.get("open_questions"),
        "onboarding_dependency_graph": _onboarding.get("artifact_dependency_graph"),
        "service_metadata": _onboarding.get("service_metadata"),
        "onboarding_schema_features": (
            _onboarding.get("capabilities", {}).get("schema_features")
            or _onboarding.get("schema_features")
        ),
    }
```

**After:**
```python
    from startd8.seeds.utils import is_omitted

    def _safe(val: Any) -> Any:
        return None if is_omitted(val) else val

    _pca_fields = {
        "onboarding_derivation_rules": _safe(_onboarding.get("derivation_rules")),
        "onboarding_resolved_parameters": _safe(_onboarding.get("resolved_artifact_parameters")),
        "onboarding_output_contracts": _safe(_onboarding.get("expected_output_contracts")),
        "onboarding_calibration_hints": _safe(_onboarding.get("design_calibration_hints")),
        "onboarding_open_questions": _safe(_onboarding.get("open_questions")),
        "onboarding_dependency_graph": _safe(_onboarding.get("artifact_dependency_graph")),
        "service_metadata": _safe(_onboarding.get("service_metadata")),
        "onboarding_schema_features": _safe(
            _onboarding.get("capabilities", {}).get("schema_features")
            or _onboarding.get("schema_features")
        ),
    }
```

**Tests:** `tests/unit/contractors/context_seed/test_shared_gpc.py`
- `test_resume_restores_generation_profile` — Profile survives resume
- `test_resume_omitted_fields_stay_none` — Omitted markers → `None` on resume path

---

## Phase B: Clean Propagation

### Step B1: Profile-aware preflight (REQ-GPC-300, REQ-GPC-301)

**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

**In `_preflight_export_contract()`, after line 1573** (onboarding JSON loaded), add profile extraction and logging:

```python
        # REQ-GPC-200/301: detect and log generation profile
        generation_profile = onboarding.get("generation_profile", "full")
        logger.info("Preflight: detected generation_profile=%s", generation_profile)
```

**At the parameter resolvability check (lines 1620-1629)**, make profile-aware:

**Before:**
```python
        has_resolvability_summary = (
            isinstance(onboarding.get("resolved_artifact_parameters"), dict)
            or isinstance(onboarding.get("parameter_resolvability"), dict)
        )
        if not has_resolvability_summary:
            errors.append(
                "Preflight: onboarding lacks parameter resolvability summary "
                "(expected resolved_artifact_parameters or parameter_resolvability)"
            )
```

**After:**
```python
        # REQ-GPC-300: relax validation for fields omitted by profile
        _RESOLVABILITY_PROFILES = {"full", "observability", "monitoring", "operator"}
        if generation_profile in _RESOLVABILITY_PROFILES:
            has_resolvability_summary = (
                isinstance(onboarding.get("resolved_artifact_parameters"), dict)
                or isinstance(onboarding.get("parameter_resolvability"), dict)
            )
            if not has_resolvability_summary:
                errors.append(
                    "Preflight: onboarding lacks parameter resolvability summary "
                    "(expected resolved_artifact_parameters or parameter_resolvability)"
                )
```

**Tests:** `tests/unit/workflows/test_preflight_gpc.py`
- `test_preflight_passes_source_profile` — Source-profile onboarding (no parameter_resolvability) passes
- `test_preflight_full_profile_unchanged` — Full-profile still enforces current rules

---

### Step B2: `ContextSeed.generation_profile` field (REQ-GPC-400)

**File:** `src/startd8/seeds/models.py`

**Add field to `ContextSeed` dataclass after line 57** (`route`):

```python
    generation_profile: Optional[str] = None
```

**Add serialization in `to_dict()` after line 91** (`route`):

```python
        if self.generation_profile is not None:
            d["generation_profile"] = self.generation_profile
```

**Tests:** `tests/unit/seeds/test_models_gpc.py`
- `test_seed_has_top_level_generation_profile` — `to_dict()` includes field
- `test_seed_default_none` — Default is `None` (backward compatible)

---

### Step B3: Builder extracts profile (REQ-GPC-401)

**File:** `src/startd8/seeds/builder.py`

**In `__init__()`, after line 83** (`_refine_suggestions`), add:

```python
        self._generation_profile: Optional[str] = None
```

**In `set_artifacts()`, after line 258** (`self._onboarding = onboarding_var`), add:

```python
            # REQ-GPC-401: extract generation profile from onboarding
            self._generation_profile = onboarding.get("generation_profile")
```

**In `_to_dict()`, add `generation_profile` to the `ContextSeed()` constructor (line 389-407):**

```python
        seed = ContextSeed(
            # ... existing fields ...
            route=self._route,
            generation_profile=self._generation_profile,  # REQ-GPC-401
        )
```

**Tests:** `tests/unit/seeds/test_builder_gpc.py`
- `test_seed_builder_sets_profile` — Builder with source-profile onboarding → seed has `generation_profile="source"`

---

### Step B4: Guard markers in seed artifacts (REQ-GPC-402)

**File:** `src/startd8/workflows/builtin/plan_ingestion_emitter.py`

**Change line 790:**

**Before:**
```python
            ex = onboarding_resolved.get("example_artifacts")
            if ex and isinstance(ex, dict):
                artifacts_out["example_artifacts"] = dict(ex)
```

**After:**
```python
            from startd8.seeds.utils import is_omitted

            ex = onboarding_resolved.get("example_artifacts")
            if ex and isinstance(ex, dict) and not is_omitted(ex):
                artifacts_out["example_artifacts"] = dict(ex)
```

**Also guard `coverage_gaps` (line 792) and `source_checksum` (line 795):**

```python
            cg = onboarding_resolved.get("coverage_gaps")
            if cg and isinstance(cg, list):
                artifacts_out["coverage_gaps"] = list(cg)
            sc = onboarding_resolved.get("source_checksum") or onboarding_resolved.get(
                "export_provenance_checksum"
            )
            if sc and isinstance(sc, str):  # str check already excludes markers
                artifacts_out["source_checksum"] = sc
                sc_val = sc
```

The `sc` check already uses `isinstance(sc, str)` which excludes dicts. The `cg` check uses `isinstance(cg, list)` which excludes dicts. Only `ex` needs the additional guard.

**Tests:** `tests/unit/workflows/test_emitter_gpc.py`
- `test_seed_artifacts_no_markers` — Onboarding with `_omitted` example_artifacts → not in seed

---

### Step B5: Type guard in service metadata (REQ-GPC-600)

**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

**Change line 696:**

**Before:**
```python
    elif onboarding:
        transport = onboarding.get("transport_protocol", "") or ""
```

**After:**
```python
    elif onboarding:
        _raw_tp = onboarding.get("transport_protocol", "")
        transport = _raw_tp if isinstance(_raw_tp, str) else ""
```

**Tests:** `tests/unit/workflows/test_infer_service_metadata_gpc.py`
- `test_service_metadata_string_transport` — Marker dict → empty string → feature-based inference fallback

---

## Phase C: Observability + Defense-in-Depth

### Step C1: Design fallback logging (REQ-GPC-500)

**File:** `src/startd8/contractors/context_seed/phases/design.py`

**In the fallback loop (lines 1046-1064), after the `if fb_val and isinstance(fb_val, dict):` check, add a branch for profile-omitted `None`:**

**Before (lines 1046-1064):**
```python
        _fb_count = 0
        for local_var, ctx_key in _fallback_map:
            if locals()[local_var] is None:
                fb_val = context.get(ctx_key)
                if fb_val and isinstance(fb_val, dict):
                    ...
                    _fb_count += 1
        if _fb_count:
            logger.info(...)
```

**After:**
```python
        _fb_count = 0
        _profile = context.get("generation_profile", "full")
        for local_var, ctx_key in _fallback_map:
            if locals()[local_var] is None:
                fb_val = context.get(ctx_key)
                if fb_val is None and _profile != "full":
                    logger.debug(
                        "DESIGN: %s skipped (omitted by %s profile)", ctx_key, _profile,
                    )
                    continue
                if fb_val and isinstance(fb_val, dict):
                    ...
                    _fb_count += 1
        if _fb_count:
            logger.info(...)
```

**Tests:** `tests/unit/contractors/context_seed/test_design_gpc.py`
- `test_design_logs_profile_omission` — Log contains profile explanation for skipped fields

---

### Step C2: Render-layer marker guard (REQ-GPC-502)

**File:** `src/startd8/contractors/artisan_phases/design_prompts/modules.py`

**In `EnrichmentModule.render()`, after line 156:**

**Before:**
```python
        param_sources = data.get("parameter_sources", {})
        if param_sources:
```

**After:**
```python
        from startd8.seeds.utils import is_omitted

        param_sources = data.get("parameter_sources", {})
        if is_omitted(param_sources):
            param_sources = {}
        if param_sources:
```

**Also guard `semantic_conventions` (line 176):**

```python
        conventions = data.get("semantic_conventions", {})
        if is_omitted(conventions):
            conventions = {}
        if conventions:
```

**Tests:** `tests/unit/contractors/artisan_phases/test_modules_gpc.py`
- `test_render_skips_marker_parameter_sources` — No `_omitted` in prompt text

---

### Step C3: Profile in consumption audit (REQ-GPC-700)

**File:** `src/startd8/contractors/context_seed/shared.py`

**In `_track_onboarding_consumption()` (line 528), add profile recording:**

**Before:**
```python
    audit = context.setdefault("_onboarding_consumption", {})
    audit.setdefault(field_name, [])
```

**After:**
```python
    audit = context.setdefault("_onboarding_consumption", {})
    if "_generation_profile" not in audit:
        audit["_generation_profile"] = context.get("generation_profile", "full")
    audit.setdefault(field_name, [])
```

**Tests:**
- `test_consumption_audit_includes_profile` — Audit dict has `_generation_profile`

---

### Step C4: Suppress false unconsumed warnings (REQ-GPC-701)

**Conditional:** Only needed if the pipeline currently emits unconsumed-field warnings. Search for any such warning emission in shared.py or other files.

If found, add:
```python
if field_value is None and generation_profile != "full":
    continue  # Intentionally omitted by profile
```

If no unconsumed warnings exist today, mark REQ-GPC-701 as N/A and revisit if/when such warnings are added.

---

## Phase D: Cap-Dev-Pipe Integration

### Step D1: Pipeline `--profile` flag (REQ-GPC-800, REQ-GPC-803)

**File:** `.cap-dev-pipe/run-cap-delivery.sh` (symlinked from `~/Documents/dev/cap-dev-pipe/`)

Add `--profile` argument parsing with validation against known values. Pass through to `contextcore manifest export --profile $PROFILE`.

### Step D2: `pipeline.env` default (REQ-GPC-801)

**File:** `.cap-dev-pipe/pipeline.env`

Add:
```bash
GENERATION_PROFILE=full  # source | monitoring | operator | sponsor | practitioner | observability | full
```

CLI `--profile` overrides env var.

### Step D3: Forward profile to plan ingestion (REQ-GPC-802)

Pass `generation_profile` into plan ingestion workflow config so the seed builder receives it via the onboarding dict (which already carries it from the ContextCore export).

**Note:** Phase D modifies cap-dev-pipe (a separate repo symlinked into startd8-sdk). Changes there should be committed in that repo.

---

## Dependency Graph

```
A1 (is_omitted)
├─ A3 (extraction guards) ← depends on A1
├─ A4 (resume guards) ← depends on A1
├─ B4 (seed artifact guards) ← depends on A1
└─ C2 (render guard) ← depends on A1

A2 (extract profile) ← independent
├─ B1 (preflight) ← depends on A2
├─ C1 (design logging) ← depends on A2
└─ C3 (consumption audit) ← depends on A2

B2 (ContextSeed field) ← independent
└─ B3 (builder sets profile) ← depends on B2

B5 (type guard) ← independent

D1-D3 (cap-dev-pipe) ← depends on Phases A-C being merged
```

**Parallelizable within Phase A:** A1 first, then A2/A3/A4 in parallel.
**Parallelizable within Phase B:** B2 first, then B1/B3/B4/B5 in parallel.

---

## Files Modified Summary

| File | Phase | Changes |
|------|-------|---------|
| `src/startd8/seeds/utils.py` | A1 | **New file** — `is_omitted()` |
| `src/startd8/contractors/context_seed/phases/plan.py` | A2, A3 | Extract profile + guard extraction loop |
| `src/startd8/contractors/context_seed/shared.py` | A4, C3 | Resume guard + consumption audit |
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | B1, B5 | Profile-aware preflight + transport type guard |
| `src/startd8/seeds/models.py` | B2 | `generation_profile` field on `ContextSeed` |
| `src/startd8/seeds/builder.py` | B3 | Builder extracts + forwards profile |
| `src/startd8/workflows/builtin/plan_ingestion_emitter.py` | B4 | Guard `_omitted` in seed artifacts |
| `src/startd8/contractors/context_seed/phases/design.py` | C1 | Profile-omission debug logging |
| `src/startd8/contractors/artisan_phases/design_prompts/modules.py` | C2 | Defense-in-depth marker guard |
| `.cap-dev-pipe/pipeline.env` + `run-cap-delivery.sh` | D | Pipeline flag + env var + forwarding |

---

## Test Files

| Test File | Phase | Tests |
|-----------|-------|-------|
| `tests/unit/seeds/test_utils.py` | A1 | 3 |
| `tests/unit/contractors/context_seed/test_plan_phase_gpc.py` | A2, A3 | 4 |
| `tests/unit/contractors/context_seed/test_shared_gpc.py` | A4 | 2 |
| `tests/unit/workflows/test_preflight_gpc.py` | B1 | 2 |
| `tests/unit/seeds/test_models_gpc.py` | B2 | 2 |
| `tests/unit/seeds/test_builder_gpc.py` | B3 | 1 |
| `tests/unit/workflows/test_emitter_gpc.py` | B4 | 1 |
| `tests/unit/workflows/test_infer_service_metadata_gpc.py` | B5 | 1 |
| `tests/unit/contractors/context_seed/test_design_gpc.py` | C1 | 1 |
| `tests/unit/contractors/artisan_phases/test_modules_gpc.py` | C2 | 1 |

**Total: 10 test files, 18 tests**

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Import cycle from `seeds.utils` into `contractors.context_seed` | `seeds/` has no imports from `contractors/` — safe direction |
| Existing tests break due to `None` where dict was expected | Existing fallback code already handles `None` (skip + defaults). Run full test suite after Phase A. |
| `context_seed_handlers.py` compat wrapper needs update | `is_omitted` is in `seeds/utils.py`, not `context_seed/` — no re-export needed |
| Cap-dev-pipe changes affect other projects | Phase D is last; all SDK changes work independently of pipeline changes |
