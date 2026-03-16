# Requirements: Generation Profile Consumer Integration (REQ-GPC)

**Status:** Draft
**Date:** 2026-03-16
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (pipeline correctness)
**Upstream:** ContextCore [REQ_GENERATION_PROFILES](~/Documents/dev/ContextCore/docs/design/requirements/REQ_GENERATION_PROFILES.md) (Phases 1-3)

---

## Problem Statement

ContextCore now emits generation-profile-scoped exports via `contextcore manifest export --profile <name>`. Under non-`full` profiles, onboarding metadata sections outside the profile's audience are replaced with `{"_omitted": "profile=<name>"}` markers.

The startd8-sdk pipeline has **zero awareness of generation profiles**. When it ingests source-profile output, `_omitted` marker dicts silently pass existing type guards (`isinstance(val, dict)` returns `True`) and propagate into:

1. **Design prompts** — `EnrichmentModule.render()` produces `- \`_omitted\`: profile=source` in the LLM prompt
2. **Context seed JSON** — `_build_seed_artifacts()` embeds marker dicts as valid artifact data
3. **Service metadata inference** — `_infer_service_metadata()` assigns a dict where a string is expected

These are silent data poisoning failures — no errors, no warnings, subtly wrong output.

### ContextCore Profile Summary

| Profile | Audience | Artifact Types Included |
|---------|----------|------------------------|
| `source` | Developer/machine | SOURCE + always-included |
| `monitoring` | Machine (automation) | MONITORING + always-included |
| `operator` | SRE | MONITORING + OPERATOR + STAKEHOLDER + always-included |
| `sponsor` | Business owner | STAKEHOLDER + always-included |
| `practitioner` | Marketing/sales | STAKEHOLDER + always-included (portal dashboards) |
| `observability` | All ops roles | All observability subcategories + always-included |
| `full` | Everyone | Everything (default, backward compatible) |

### Onboarding Sections Subject to Profile Gating

| Omitted Section | Normal Type | Consumed By |
|----------------|-------------|-------------|
| `derivation_rules` | `Dict[str, List[Dict]]` | Design phase fallback map |
| `design_calibration_hints` | `Dict[artifact_type, Dict]` | `extract_guidance()` depth hints |
| `expected_output_contracts` | `Dict[str, Dict]` | Design phase fallback map |
| `parameter_resolvability` | `Dict[artifact_id, Dict]` | Preflight validation |
| `artifact_dependency_graph` | `Dict[str, List[str]]` | Design phase ordering |

---

## Requirements

### Layer 1: Omitted Marker Detection (Foundation)

#### REQ-GPC-100: `is_omitted()` Utility Function

**Status:** Draft
**Priority:** P0
**File:** `src/startd8/seeds/utils.py` (new file)

The SDK SHALL provide a shared utility to detect ContextCore profile-omitted markers:

```python
def is_omitted(value: Any) -> bool:
    """Return True if value is a ContextCore profile-omitted marker."""
    return isinstance(value, dict) and "_omitted" in value
```

**Why:** Every consumer of onboarding fields needs this check. The marker format `{"_omitted": "profile=source"}` is a ContextCore contract — centralizing detection means one place to update if the format evolves.

**Acceptance:**
1. `is_omitted({"_omitted": "profile=source"})` returns `True`
2. `is_omitted({"dashboard": {...}})` returns `False`
3. `is_omitted(None)` returns `False`
4. `is_omitted([])` returns `False`

---

### Layer 2: Extraction Guards (Prevent Ingestion)

#### REQ-GPC-200: PLAN Phase Extracts `generation_profile`

**Status:** Draft
**Priority:** P0
**File:** `src/startd8/contractors/context_seed/phases/plan.py` (~line 135)

The PLAN phase handler SHALL extract `generation_profile` from the onboarding dict and store it in context:

```python
context["generation_profile"] = _onboarding.get("generation_profile", "full")
```

**Why:** Every downstream decision point (preflight, fallback selection, prompt assembly, consumption tracking) needs the active profile. Extracting once at PLAN — the earliest point where onboarding is read — ensures availability via the shared `context` dict.

**Acceptance:** After PLAN phase, `context["generation_profile"]` is one of `"source"`, `"monitoring"`, `"operator"`, `"sponsor"`, `"practitioner"`, `"observability"`, or `"full"` (defaulting to `"full"` for pre-profile exports).

#### REQ-GPC-201: Extraction Loop Skips Omitted Fields

**Status:** Draft
**Priority:** P0
**File:** `src/startd8/contractors/context_seed/phases/plan.py` (lines 135-157) + `src/startd8/contractors/context_seed/shared.py` (lines 383-404)

The 8-field extraction loop SHALL skip fields whose values are omitted markers, setting them to `None` in context:

```python
for field_key, ctx_key in _ONBOARDING_FIELDS:
    raw = _onboarding.get(field_key)
    context[ctx_key] = None if is_omitted(raw) else raw
```

**Why:** The current code assigns marker dicts into context. These flow to the design phase fallback map where `isinstance(marker, dict)` returns `True`, accepting markers as valid calibration data. Setting to `None` activates existing fallback logic (LOC-based heuristics, complexity defaults).

**Acceptance:** When onboarding contains `{"derivation_rules": {"_omitted": "profile=source"}}`, `context["onboarding_derivation_rules"]` is `None`, not the marker dict.

#### REQ-GPC-202: Resume/Recovery Preserves Profile

**Status:** Draft
**Priority:** P0
**File:** `src/startd8/contractors/context_seed/shared.py` (`_ensure_context_loaded()`, ~line 383)

`_ensure_context_loaded()` SHALL restore `generation_profile` alongside the 8 onboarding fields during session resume:

```python
if "generation_profile" not in context:
    context["generation_profile"] = _onboarding.get("generation_profile", "full")
```

**Why:** Contractor workflows support session resume. If `generation_profile` isn't restored, the resumed session loses profile awareness and may re-ingest omitted fields as valid data. The "only restore if not already in context" pattern matches existing fields at line 400.

**Acceptance:** After session resume from a source-profile seed, `context["generation_profile"]` is `"source"`.

---

### Layer 3: Preflight Validation (Fail Fast)

#### REQ-GPC-300: Profile-Aware Preflight Validation

**Status:** Draft
**Priority:** P1
**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py` (`_preflight_export_contract()`, ~line 1540)

Preflight validation SHALL read `generation_profile` from onboarding and relax validation for fields known to be omitted under that profile:

| Profile | Fields Validated | Fields Skipped |
|---------|-----------------|----------------|
| `full` | All (current behavior) | None |
| `source` | `artifact_manifest_path`, `project_context_path`, `coverage`, `source_checksum` | `parameter_resolvability`, `derivation_rules`, `calibration_hints` |
| `monitoring` | All observability fields | Source artifact paths |
| `operator` | All observability fields | Source artifact paths |
| `sponsor` | Stakeholder fields + contracts/calibration | Derivation rules, dependency graph, parameter_resolvability |
| `practitioner` | Same as sponsor | Same as sponsor |
| `observability` | All observability fields | Source artifact paths |

**Why:** Under source profile after REQ-GPC-201, `parameter_resolvability` is `None`. Without profile-aware relaxation, preflight fails with a spurious error demanding a field that was intentionally excluded.

**Acceptance:**
1. `--profile source` export output passes preflight without errors or false warnings about missing observability fields
2. `--profile full` export output passes preflight identically to current behavior

#### REQ-GPC-301: Preflight Logs Detected Profile

**Status:** Draft
**Priority:** P2
**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

Preflight SHALL log the detected generation profile at INFO level:

```python
logger.info("Preflight: detected generation_profile=%s", generation_profile)
```

**Acceptance:** Pipeline logs contain the generation profile for every run.

---

### Layer 4: Seed Assembly (Clean Propagation)

#### REQ-GPC-400: `ContextSeed` Carries `generation_profile`

**Status:** Draft
**Priority:** P1
**File:** `src/startd8/seeds/models.py` (`ContextSeed` dataclass, ~line 34)

`ContextSeed` SHALL include a `generation_profile` field:

```python
@dataclass
class ContextSeed:
    # ... existing fields ...
    generation_profile: Optional[str] = None
```

**Why:** Promotes profile from buried `seed.onboarding["generation_profile"]` to top-level contract surface. `onboarding` is `Optional[Dict[str, Any]]` with no schema — extracting from it requires defensive coding at every call site. Existing seeds without the field default to `None` (interpreted as `"full"`).

**Acceptance:** `context-seed.json` contains `"generation_profile": "source"` at top level.

#### REQ-GPC-401: Seed Builder Sets Profile from Onboarding

**Status:** Draft
**Priority:** P1
**File:** `src/startd8/seeds/builder.py` (`SeedBuilder.set_artifacts()`, ~line 198)

`set_artifacts()` SHALL extract `generation_profile` from the onboarding dict:

```python
if onboarding:
    self._generation_profile = onboarding.get("generation_profile", "full")
```

And `build()` SHALL include it in the final `ContextSeed`.

**Why:** Follows the established pattern — builder already extracts `source_checksum` from onboarding the same way (~line 798).

**Acceptance:** A seed built from source-profile onboarding has `generation_profile="source"`.

#### REQ-GPC-402: `_build_seed_artifacts()` Guards Marker Dicts

**Status:** Draft
**Priority:** P1
**File:** `src/startd8/workflows/builtin/plan_ingestion_emitter.py` (`_build_seed_artifacts()`, ~line 781)

Seed artifact assembly SHALL use `is_omitted()` before embedding onboarding fields:

```python
if ex and isinstance(ex, dict) and not is_omitted(ex):
    artifacts_out["example_artifacts"] = dict(ex)
```

**Why:** Current code at ~line 790 does `isinstance(ex, dict)` — the `_omitted` marker passes this check. The marker gets embedded as `{"example_artifacts": {"_omitted": "profile=source"}}`. Downstream code iterating `example_artifacts` processes `_omitted` as an artifact type.

**Acceptance:** Seeds built from source-profile output contain no `_omitted` marker values in the `artifacts` section.

---

### Layer 5: Design Phase (Correct Behavior)

#### REQ-GPC-500: Fallback Map Logs Profile Omissions

**Status:** Draft
**Priority:** P2
**File:** `src/startd8/contractors/context_seed/phases/design.py` (fallback map, ~line 1038)

When a fallback is skipped because the profile omitted it, the log SHALL explain:

```python
if fb_val is None and profile != "full":
    logger.debug("DESIGN: %s skipped (omitted by %s profile)", ctx_key, profile)
```

**Why:** The existing fallback code already handles `None` correctly (skip + use defaults). REQ-GPC-201 ensures omitted fields are `None`. This requirement adds observability — when debugging why heuristics were used instead of calibration hints.

**Acceptance:** Source-profile runs produce design prompts using LOC-based heuristics with log lines explaining why.

#### REQ-GPC-501: `extract_guidance()` Depends on REQ-GPC-201

**Status:** Draft (documentation-only)
**Priority:** P2
**File:** `src/startd8/contractors/context_seed/seed_mapping.py` (`extract_guidance()`, ~line 140)

`extract_guidance()` already handles `calibration_hints=None` gracefully (the `if calibration_hints and task.artifact_types_addressed:` guard short-circuits). No code change needed IF REQ-GPC-201 is implemented.

**Why (documented dependency):** The current code is accidentally correct for `None` but NOT for marker dicts — `{"_omitted": "..."}` is truthy, passes the guard, and `calibration_hints.get("dashboard")` returns `None`, silently losing depth hints.

**Acceptance:** `extract_guidance(task, calibration_hints=None)` returns guidance without depth_hint.

#### REQ-GPC-502: `EnrichmentModule.render()` Defense-in-Depth Guard

**Status:** Draft
**Priority:** P2
**File:** `src/startd8/contractors/artisan_phases/design_prompts/modules.py` (`EnrichmentModule.render()`, ~line 143)

The render method SHALL include a defense-in-depth guard against marker dicts:

```python
if is_omitted(param_sources):
    return PromptFragment(text="", token_estimate=0)
```

**Why:** This is the most dangerous failure mode — prompt poisoning. Prevented upstream by REQ-GPC-201, but if someone later reads onboarding directly instead of from context, the rendering layer has no defense.

**Acceptance:** Design prompts from source-profile seeds never contain `_omitted` as a parameter name.

---

### Layer 6: Service Metadata Inference (Type Safety)

#### REQ-GPC-600: `_infer_service_metadata()` Type Guard

**Status:** Draft
**Priority:** P1
**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py` (`_infer_service_metadata()`, ~line 658)

Service metadata inference SHALL guard against marker values in raw onboarding fields:

```python
raw_transport = onboarding.get("transport_protocol", "")
transport = raw_transport if isinstance(raw_transport, str) else ""
```

**Why:** Unlike onboarding fields gated by REQ-GPC-201 at extraction time, `_infer_service_metadata()` reads directly from the raw onboarding dict during seed assembly — before the extraction layer runs. A local type check is needed.

**Acceptance:** Source-profile onboarding with marker values produces service metadata with empty-string transport (triggering feature-based inference fallback) instead of dict-typed transport.

---

### Layer 7: Consumption Tracking (Observability)

#### REQ-GPC-700: Consumption Tracking Records Profile

**Status:** Draft
**Priority:** P2
**File:** `src/startd8/contractors/context_seed/shared.py` (`_track_onboarding_consumption()`, ~line 524)

Consumption tracking SHALL include `generation_profile` in the audit record:

```python
audit = context.setdefault("_onboarding_consumption", {})
audit["_generation_profile"] = context.get("generation_profile", "full")
```

**Why:** Without the profile, "derivation_rules: never consumed" is ambiguous — bug vs intentional omission.

**Acceptance:** Consumption audit includes `_generation_profile`.

#### REQ-GPC-701: No "Unconsumed" Warnings for Omitted Fields

**Status:** Draft
**Priority:** P2
**File:** `src/startd8/contractors/context_seed/shared.py`

The pipeline SHALL NOT warn for fields that are `None` due to profile omission:

```python
if field_value is None and generation_profile != "full":
    continue  # Intentionally omitted, not unconsumed
```

**Why:** False warnings erode trust. Source-profile runs producing 5 spurious warnings teaches operators to ignore all warnings.

**Acceptance:** Source-profile runs produce zero spurious unconsumed-field warnings.

---

### Layer 8: Cap-Dev-Pipe Integration

#### REQ-GPC-800: Pipeline Accepts `--profile` Flag

**Status:** Draft
**Priority:** P1
**File:** `.cap-dev-pipe/run-cap-delivery.sh` (symlinked from `~/Documents/dev/cap-dev-pipe/`)

`run-pipeline.sh` SHALL accept a `--profile` flag and pass it through to `contextcore manifest export`:

```bash
./run-pipeline.sh --profile operator --plan plan.md
# Internally: contextcore manifest export ... --profile operator
```

**Acceptance:** `./run-pipeline.sh --profile source` produces source-scoped export artifacts.

#### REQ-GPC-801: `pipeline.env` Supports `GENERATION_PROFILE`

**Status:** Draft
**Priority:** P1
**File:** `.cap-dev-pipe/pipeline.env`

`pipeline.env` SHALL support a `GENERATION_PROFILE` variable defaulting to `full`:

```bash
GENERATION_PROFILE=full  # source | monitoring | operator | sponsor | practitioner | observability | full
```

CLI `--profile` overrides the env var.

**Acceptance:** Setting `GENERATION_PROFILE=operator` in `pipeline.env` and running `./run-pipeline.sh` (no `--profile`) produces operator-scoped output.

#### REQ-GPC-802: Pipeline Forwards Profile to Plan Ingestion

**Status:** Draft
**Priority:** P1
**File:** `.cap-dev-pipe/run-plan-ingestion.sh` or plan ingestion workflow config

The pipeline SHALL pass `generation_profile` to the plan ingestion workflow configuration:

```python
workflow_config = {
    "generation_profile": generation_profile,
    # ...
}
```

**Acceptance:** Context seed produced by plan ingestion contains the profile value passed via `--profile`.

#### REQ-GPC-803: Pipeline Validates Profile Before Export

**Status:** Draft
**Priority:** P2
**File:** `.cap-dev-pipe/run-cap-delivery.sh`

Invalid `--profile` values SHALL produce a clear error before export:

```bash
./run-pipeline.sh --profile invalid
# Error: Invalid generation profile 'invalid'. Valid values: source, monitoring, operator, sponsor, practitioner, observability, full
```

**Acceptance:** Invalid profile values produce a pipeline-level error before any export is attempted.

---

## Implementation Phases

### Phase A: Foundation (~26 lines, must ship together)

| Req | Description | File | Est. Lines |
|-----|-------------|------|-----------|
| REQ-GPC-100 | `is_omitted()` utility | `seeds/utils.py` (new) | ~5 |
| REQ-GPC-200 | Extract `generation_profile` at PLAN | `context_seed/phases/plan.py` | ~3 |
| REQ-GPC-201 | Skip omitted fields at extraction | `context_seed/phases/plan.py` + `shared.py` | ~15 |
| REQ-GPC-202 | Restore profile on resume | `context_seed/shared.py` | ~3 |

**Prevents all silent data poisoning.**

### Phase B: Clean Propagation (~33 lines)

| Req | Description | File | Est. Lines |
|-----|-------------|------|-----------|
| REQ-GPC-300 | Profile-aware preflight | `plan_ingestion_workflow.py` | ~15 |
| REQ-GPC-301 | Log detected profile | `plan_ingestion_workflow.py` | ~2 |
| REQ-GPC-400 | Top-level seed field | `seeds/models.py` | ~3 |
| REQ-GPC-401 | Builder sets profile | `seeds/builder.py` | ~5 |
| REQ-GPC-402 | Guard markers in seed artifacts | `plan_ingestion_emitter.py` | ~5 |
| REQ-GPC-600 | Type guard in service metadata | `plan_ingestion_workflow.py` | ~3 |

**Ensures clean data flow from export to seed.**

### Phase C: Observability + Defense-in-Depth (~16 lines)

| Req | Description | File | Est. Lines |
|-----|-------------|------|-----------|
| REQ-GPC-500 | Design fallback logging | `context_seed/phases/design.py` | ~5 |
| REQ-GPC-502 | Render-layer marker guard | `design_prompts/modules.py` | ~3 |
| REQ-GPC-700 | Profile in consumption audit | `context_seed/shared.py` | ~3 |
| REQ-GPC-701 | Suppress false warnings | `context_seed/shared.py` | ~5 |

**Makes the pipeline self-documenting.**

### Phase D: Cap-Dev-Pipe (~25 lines)

| Req | Description | File | Est. Lines |
|-----|-------------|------|-----------|
| REQ-GPC-800 | Pipeline `--profile` flag | `run-cap-delivery.sh` | ~10 |
| REQ-GPC-801 | `GENERATION_PROFILE` env var | `pipeline.env` | ~2 |
| REQ-GPC-802 | Forward profile to plan ingestion | Pipeline config | ~8 |
| REQ-GPC-803 | Validate profile before export | `run-cap-delivery.sh` | ~5 |

---

## Total Estimated Effort

~100 lines across 10 files. Phase A is the critical path — without it, source-profile exports produce silently corrupt seeds.

---

## Test Plan

### Phase A Tests

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_is_omitted_detects_markers` | REQ-GPC-100 |
| 2 | `test_is_omitted_rejects_normal_dicts` | REQ-GPC-100 |
| 3 | `test_is_omitted_handles_none_and_list` | REQ-GPC-100 |
| 4 | `test_plan_phase_extracts_generation_profile` | REQ-GPC-200 |
| 5 | `test_plan_phase_defaults_to_full` | REQ-GPC-200 |
| 6 | `test_plan_phase_sets_omitted_fields_to_none` | REQ-GPC-201 |
| 7 | `test_plan_phase_preserves_non_omitted_fields` | REQ-GPC-201 |
| 8 | `test_resume_restores_generation_profile` | REQ-GPC-202 |
| 9 | `test_resume_omitted_fields_stay_none` | REQ-GPC-202 |

### Phase B Tests

| # | Test | Validates |
|---|------|-----------|
| 10 | `test_preflight_passes_source_profile` | REQ-GPC-300 |
| 11 | `test_preflight_full_profile_unchanged` | REQ-GPC-300 |
| 12 | `test_seed_has_top_level_generation_profile` | REQ-GPC-400 |
| 13 | `test_seed_builder_sets_profile` | REQ-GPC-401 |
| 14 | `test_seed_artifacts_no_markers` | REQ-GPC-402 |
| 15 | `test_service_metadata_string_transport` | REQ-GPC-600 |

### Phase C Tests

| # | Test | Validates |
|---|------|-----------|
| 16 | `test_design_logs_profile_omission` | REQ-GPC-500 |
| 17 | `test_render_skips_marker_parameter_sources` | REQ-GPC-502 |
| 18 | `test_consumption_audit_includes_profile` | REQ-GPC-700 |
| 19 | `test_no_spurious_unconsumed_warnings` | REQ-GPC-701 |

---

## Future: Audience-Aware Design Enhancements (REQ-GPC-9xx)

Not required for correctness but improves quality for non-full profiles.

#### REQ-GPC-900: Profile-Specific Dashboard Pattern Default

When the seed contains `generation_profile`, the design phase SHOULD set a default `dashboard_pattern`:

| Profile | Default `dashboard_pattern` | Default `audience` |
|---------|---------------------------|-------------------|
| `operator` | `operational` | `operator` |
| `sponsor` | `business_health` | `sponsor` |
| `practitioner` | `portal` | `practitioner` |
| `full` / `observability` | `operational` (current) | `operator` |

#### REQ-GPC-901: Practitioner Portal Content Pattern

Dashboard generation for `practitioner` profile SHOULD produce portal-style dashboards with plain-language headings, navigation links, domain-native KPIs, "start here" sections, and zero assumed Grafana literacy.

---

## Relationship to Existing Work

| Document | Relationship |
|----------|-------------|
| ContextCore [REQ_GENERATION_PROFILES](~/Documents/dev/ContextCore/docs/design/requirements/REQ_GENERATION_PROFILES.md) | Producer side — defines `_omitted` marker contract and `_SECTION_PROFILES` |
| ContextCore [REQ_CROSS_CUTTING_CONTEXT_LOSS](~/Documents/dev/ContextCore/docs/design/requirements/REQ_CROSS_CUTTING_CONTEXT_LOSS.md) | Origin — identified the 200KB overhead problem |
| [Cross-Cutting Context Loss Analysis](../kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) | Origin — Seed Complexity Audit identified 90% overhead |
| [KAIZEN_PLAN_INGESTION_REQUIREMENTS](../plan-ingestion/KAIZEN_PLAN_INGESTION_REQUIREMENTS.md) | Related — plan ingestion is the primary consumer path |
| [Artisan pipeline contract](../../src/startd8/contractors/contracts/artisan-pipeline.contract.yaml) | Related — phase contracts may need profile-awareness |

---

## Non-Goals

- Changing the `_omitted` marker format (ContextCore contract)
- Adding new onboarding fields for audience-specific data (use `parameters.audience` on ArtifactSpec)
- Multiple dashboard variants per service in a single run (use sequential profile runs)
- Automatic profile selection based on plan content (always explicit)
- Profile-specific validation rules (quality gates apply uniformly)
