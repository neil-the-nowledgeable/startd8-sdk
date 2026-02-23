# Design Prompt Tiered Context Rendering — Requirements

> **Version:** 1.0.0
> **Status:** Planned (all requirements)
> **Date:** 2026-02-23
> **Scope:** Progressive-disclosure rendering of `additional_context` fields in the DESIGN phase prompt, with tier classification, token-budget-aware compression, and backward-compatible integration
> **Extends:** `ARTISAN_REQUIREMENTS.md` Layer 3 (AR-3xx Design Phase)
> **Depends on:** AR-300 (design document generation), CCD-201 (two-tier context model)

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [Design Principles](#2-design-principles)
3. [Tier Classification Registry](#3-tier-classification-registry)
4. [Requirements](#4-requirements)
   - [Layer 1: Tier Registry & Entry Point (TC-1xx)](#layer-1-tier-registry--entry-point-tc-1xx)
   - [Layer 2: Token Budget & Progressive Compression (TC-2xx)](#layer-2-token-budget--progressive-compression-tc-2xx)
   - [Layer 3: Integration (TC-3xx)](#layer-3-integration-tc-3xx)
   - [Layer 4: Backward Compatibility (TC-4xx)](#layer-4-backward-compatibility-tc-4xx)
   - [Layer 5: Test Coverage (TC-5xx)](#layer-5-test-coverage-tc-5xx)
5. [Data Flow Diagram](#5-data-flow-diagram)
6. [Traceability Matrix](#6-traceability-matrix)
7. [Status Dashboard](#7-status-dashboard)
8. [Verification](#8-verification)
9. [Related Documents](#9-related-documents)

---

## 1. Motivation

The DESIGN phase's `_generate_design()` method in `design_documentation.py` renders all `additional_context` fields into a flat bold-key blob:

```python
for k, v in context.additional_context.items():
    if isinstance(v, str):
        ctx_parts.append(f"**{k}:** {v}")
    else:
        ctx_parts.append(f"**{k}:**\n{json.dumps(v, indent=2, default=str)}")
```

This creates three problems:

1. **Token waste on low-priority metadata.** Fields like `domain`, `feature_id`, `calibration_override_source`, and `wave_context` carry metadata that rarely influences design decisions, yet each consumes a bold-key line identical in visual weight to critical constraints like `contested_files` or `api_signatures`. With 33+ fields populated for a typical manifest-rich task, the additional_context block can exceed 9,000 tokens — nearly half a typical prompt budget.

2. **Signal-to-noise degradation.** The LLM receives `critical_parameters_checklist` (design-critical) at the same formatting level as `import_conventions` (nice-to-have). Human reviewers scanning prompts for debugging see the same flat wall. Important constraints get buried in metadata.

3. **Unbounded JSON payloads.** Fields like `parameter_sources`, `derivation_rules`, `resolved_parameters`, and `output_contracts` are dicts that get `json.dumps(indent=2)` treatment. A single artifact type's resolved parameters can expand to 2,000+ chars of indented JSON, most of which the LLM will not reference in the design.

### Prompt size estimates (current behavior)

| Scenario | User Prompt | additional_context portion |
|----------|-------------|---------------------------|
| Minimal (no manifest, no calibration) | ~1,000 chars | ~400 chars (2-3 fields) |
| Typical (manifest + calibration) | ~5,000-8,000 chars | ~3,000-5,000 chars (15-20 fields) |
| Refine path (prior design + feedback) | ~12,000-20,000 chars | ~3,000-5,000 chars (same fields) |
| Maximum (all 33 fields + JSON payloads) | ~25,000-35,000 chars | ~15,000-25,000 chars |

The maximum case sends ~6,000-9,000 tokens of context, most of which is T2/T3 metadata that could be collapsed or dropped without affecting design quality.

---

## 2. Design Principles

| Principle | Source | Compliance |
|-----------|--------|------------|
| Progressive Disclosure | This document | Critical fields rendered first and in full; supporting fields collapsed; metadata condensed to a single line. Section headers (`### Critical Context`, `### Supporting Information`, etc.) give the LLM a navigable structure |
| Budget-Aware Rendering | This document | Soft token budget (4,000 tokens) with progressive compression: T3 dropped first, T2 collapsed to one-liners, T1 strings truncated to 500 chars. T0 never compressed |
| Mottainai Rule 2: Forward, Don't Regenerate | `MOTTAINAI_DESIGN_PRINCIPLE.md` | Reuses existing `format_constraints()` pattern from `prompt_utils.py`. No new modules — extends the existing prompt utility file. Existing `_task_to_feature_context()` population logic is unchanged |
| Mottainai Rule 6: Measure the Gap | `MOTTAINAI_DESIGN_PRINCIPLE.md` | Token estimates enable measurement of before/after prompt sizes. The tier registry makes field-level contribution visible |
| Separation of Concerns | General | Tier classification (registry) is separated from rendering logic (helpers) and integration point (`_generate_design`). Population (`_task_to_feature_context`) is untouched |
| Declarative Configuration | This document | `CONTEXT_FIELD_TIERS` is a static dict mapping field names to tier integers. New fields added in `_task_to_feature_context()` automatically get T2 (medium) rendering via the unknown-field default |

---

## 3. Tier Classification Registry

All 33 fields currently populated in `_task_to_feature_context()` are classified into four tiers:

### T0 — Critical (always full, never compressed)

Fields that drive design decisions, carry authoritative constraints, or gate correctness. The LLM must see these verbatim.

| Field | Rationale |
|-------|-----------|
| `critical_parameters_checklist` | Instructs LLM to enumerate critical params; directly gates implementation fidelity |
| `plan_architecture` | FOUNDATION prefix — authoritative architecture from plan ingestion |
| `api_signatures` | Plan-specified API signatures that must be preserved exactly |
| `api_signature_verification` | Verification instruction for plan-specified signatures |
| `transport_protocol` | Protocol constraint that gates health checks, client config |
| `contested_files` | SHARED FILE WARNING — design must coordinate with other tasks |
| `collision_resolution` | DESIGN COLLISION ALERT — must-follow constraints from collision detection |

### T1 — High (full rendering, truncatable under extreme budget pressure)

Fields that frame scope, constraints, and design direction. Rendered in full under normal conditions; string values may truncate to 500 chars only when budget is critically exceeded.

| Field | Rationale |
|-------|-----------|
| `project_goals` | Benefit-driven framing; scopes design intent |
| `constraints_from_manifest` | Manifest-sourced constraints (severity-tagged) |
| `shared_modules` | Coordination warning for multi-task target files |
| `scope_boundary` | Explicit out-of-scope items (negative scope) |
| `refine_suggestions` | Pre-validated architectural review recommendations |
| `plan_risks` | FOUNDATION prefix — risk analysis from plan ingestion |
| `plan_verification_strategy` | FOUNDATION prefix — verification strategy from plan |
| `complexity_guidance` | High-dimension complexity alerts |
| `dependency_designs` | Designs of upstream dependency tasks |
| `artifact_dependencies` | Known inter-artifact dependency graph |
| `staleness_guidance` | Stale/current file classification for design focus |

### T2 — Medium (collapsed rendering; default for unknown fields)

Fields that inform but do not constrain. Dicts show top-level keys with `{...N items}` hints; strings >300 chars are truncated; lists show count + first item preview. Unknown/unregistered fields default to this tier.

| Field | Rationale |
|-------|-----------|
| `parameter_sources` | JSON payload — top-level keys sufficient for design |
| `derivation_rules` | JSON payload — artifact-type keys sufficient |
| `resolved_parameters` | JSON payload — parameter names sufficient; values are in requirements_text |
| `output_contracts` | JSON payload — contract type keys sufficient |
| `lane_peer_designs` | Already token-budgeted by `_apply_lane_peer_token_budget()` |
| `domain_concepts` | Informational; design proceeds without them |
| `objectives` | Informational summary of manifest objectives |
| `open_questions` | Awareness items, not constraints |
| `semantic_conventions` | Naming conventions; informational |
| `prior_designs` | Cross-lane summaries (already truncated to 5 items) |

### T3 — Low (metadata line; droppable under budget pressure)

Metadata with minimal direct design impact. Rendered as a single pipe-delimited line. Dropped entirely when over budget.

| Field | Rationale |
|-------|-----------|
| `domain` | Classification label |
| `siblings` | Sibling feature list |
| `feature_id` | Identifier |
| `domain_reasoning` | Explanation of domain classification |
| `import_conventions` | Informational style hint |
| `depth_guidance` | Already influences sections/tokens via calibration |
| `wave_context` | Parallelism note |
| `calibration_override_source` | Debug/provenance metadata |
| `plan_delta` | Section mismatch diagnostic |
| `design_doc_sections` | Already controls section list via calibration |

### Rendering Summary

| Tier | Section Header | Rendering | Budget Behavior |
|------|---------------|-----------|-----------------|
| T0 | `### Critical Context` | Full (bold-key + value/JSON, identical to current) | Never compressed |
| T1 | `### Design Constraints` | Full (bold-key + value/JSON, identical to current) | String values truncate to 500 chars under extreme pressure |
| T2 | `### Supporting Information` | Collapsed: dicts → top-level keys with `{...N items}`, strings >300 chars → `[...N more chars]`, lists → count + first-item preview | Collapsed to one-liners if over budget |
| T3 | `### Metadata` | Single pipe-delimited line (`key: value | key: value`) | Dropped entirely if over budget |

---

## 4. Requirements

### Layer 1: Tier Registry & Entry Point (TC-1xx)

#### TC-100: Tier Classification Registry

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py`

Define a module-level constant `CONTEXT_FIELD_TIERS: dict[str, int]` mapping all 33 known `additional_context` field names to their tier (0, 1, 2, or 3). The registry is the single source of truth for tier assignments.

**Acceptance criteria:**
1. `CONTEXT_FIELD_TIERS` is a `dict[str, int]` importable from `prompt_utils`.
2. All 33 fields listed in Section 3 are present with correct tier values.
3. No field is mapped to a value outside `{0, 1, 2, 3}`.
4. The registry is declarative (static dict, not computed at runtime).

#### TC-101: `format_tiered_context()` Entry Point

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py`

Provide a `format_tiered_context(additional_context: dict[str, Any], *, token_budget: int = 4000) -> str` function that renders the context dict into a structured markdown string with tier-based progressive disclosure.

**Acceptance criteria:**
1. Signature is `format_tiered_context(additional_context: dict[str, Any], *, token_budget: int = 4000) -> str`.
2. Returns `"None"` for empty or `None` input (backward compatibility with current behavior).
3. Fields are grouped by tier, with each non-empty tier getting a markdown `###` header.
4. Empty tiers (no fields present for that tier) omit their section header entirely.
5. Tiers are rendered in order: T0, T1, T2, T3.
6. The function is exported in `prompt_utils` and re-exported via `artisan_phases/prompts/__init__.py`.

#### TC-102: T0/T1 Full Rendering

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py` (internal helper `_render_full`)

T0 and T1 fields are rendered with the same fidelity as the current inline loop: bold key, string values inline, non-string values as `json.dumps(indent=2)`.

**Acceptance criteria:**
1. String values render as `**{key}:** {value}`.
2. Non-string values render as `**{key}:**\n{json.dumps(value, indent=2, default=str)}`.
3. Output for T0/T1 fields is byte-identical to the current inline loop for the same input.

#### TC-103: T2 Collapsed Rendering

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py` (internal helper `_render_collapsed`)

T2 fields are rendered with collapsed summaries to reduce token usage while preserving signal:

**Acceptance criteria:**
1. **Dict values:** Top-level keys listed with child-count hints. Example: `**resolved_parameters:** embedding_service {…3 items}, vector_db {…5 items}`.
2. **String values >300 chars:** Truncated with suffix. Example: `**parameter_sources:** Parameter sources (from ContextCore manifest)... [...1,247 more chars]`.
3. **String values ≤300 chars:** Rendered in full (same as T0/T1).
4. **List values:** Show count and first-item preview. Example: `**open_questions:** 5 items: "What retry strategy should..." [...]`.
5. **Other types:** Fall back to `_render_full` behavior.

#### TC-104: T3 Metadata Line Rendering

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py` (internal helper `_render_metadata_line`)

All T3 fields are rendered as a single pipe-delimited line to minimize token consumption.

**Acceptance criteria:**
1. All T3 fields present in the input are joined as `key: value | key: value | ...`.
2. Multi-line string values are collapsed to their first line.
3. Non-string values are converted to `str()` and truncated to 60 chars.
4. The entire T3 block is a single paragraph (no newlines between fields).
5. If only one T3 field is present, no trailing pipe.

---

### Layer 2: Token Budget & Progressive Compression (TC-2xx)

#### TC-200: Soft Token Budget

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py`

Define a default token budget of 4,000 tokens for the `additional_context` block. Token estimation uses `len(chars) // 4`, consistent with the existing `_apply_lane_peer_token_budget()` in `context_seed_handlers.py`.

**Acceptance criteria:**
1. Default budget constant `_ADDITIONAL_CONTEXT_TOKEN_BUDGET = 4000` is defined.
2. The `token_budget` parameter on `format_tiered_context()` defaults to this constant.
3. Token estimation formula is `len(rendered_text) // 4`.

#### TC-201: Progressive Compression — T3 Drop

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py`

When the fully-rendered output exceeds the token budget, the first compression step drops the T3 metadata section entirely.

**Acceptance criteria:**
1. After initial rendering, if estimated tokens > budget, the T3 section is removed.
2. If removing T3 brings the output under budget, no further compression is applied.
3. T0 fields are not affected.

#### TC-202: Progressive Compression — T2 Collapse to One-Liners

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py`

If dropping T3 is insufficient, the second compression step re-renders T2 fields as one-liners (key + first 80 chars of stringified value).

**Acceptance criteria:**
1. T2 re-rendering uses a `_render_oneline(key, value)` helper: `**{key}:** {str(value)[:80]}...`.
2. Dict values show only their top-level key count: `**{key}:** {len(value)} entries`.
3. If collapsing T2 brings the output under budget, no further compression is applied.
4. T0 fields are not affected.

#### TC-203: Progressive Compression — T1 String Truncation

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py`

If dropping T3 and collapsing T2 are both insufficient, the third compression step truncates T1 string values to 500 chars. Non-string T1 values are not truncated.

**Acceptance criteria:**
1. Only string values in T1 are truncated; non-string values (lists, dicts) are left intact.
2. Truncated strings end with `\n... [truncated to 500 chars]`.
3. T0 fields are never affected by any compression step.
4. This is the final compression step — no further compression is attempted beyond this.

---

### Layer 3: Integration (TC-3xx)

#### TC-300: Replace Inline Loop in `_generate_design()`

**Status:** planned
**Source:** `src/startd8/contractors/artisan_phases/design_documentation.py`

Replace the 12-line formatting loop (lines ~1184-1196) in `_generate_design()` with a call to `format_tiered_context()`.

**Acceptance criteria:**
1. The `if context.additional_context:` block is replaced with:
   ```python
   from startd8.contractors.prompt_utils import format_tiered_context
   additional_context_str = format_tiered_context(context.additional_context)
   ```
2. The `else: additional_context_str = "None"` branch is removed (handled by `format_tiered_context`).
3. Net change is approximately -9 lines.
4. The `json` import in `design_documentation.py` is retained (used elsewhere in the module).

#### TC-301: Re-Export from Prompts Package

**Status:** planned
**Source:** `src/startd8/contractors/artisan_phases/prompts/__init__.py`

Re-export `format_tiered_context` from the prompts package for consistency with existing `format_constraints` and `format_prompt` exports.

**Acceptance criteria:**
1. `from startd8.contractors.prompt_utils import format_tiered_context` is added to the prompts `__init__.py`.
2. `format_tiered_context` is importable from `startd8.contractors.artisan_phases.prompts`.

---

### Layer 4: Backward Compatibility (TC-4xx)

#### TC-400: Empty Input Returns "None"

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py`

When `additional_context` is empty (`{}`) or `None`, `format_tiered_context()` returns the string `"None"`, preserving the current behavior of the inline loop's else branch.

**Acceptance criteria:**
1. `format_tiered_context({})` returns `"None"`.
2. `format_tiered_context(None)` returns `"None"` (defensive, even though callers pass `{}`).

#### TC-401: FeatureContext Unchanged

**Status:** planned (constraint, not code change)

The `FeatureContext` dataclass in `design_documentation.py` is not modified. The `additional_context: dict[str, Any]` field retains its current type and default.

**Acceptance criteria:**
1. No fields added, removed, or retyped on `FeatureContext`.
2. The `additional_context` field remains `dict[str, Any]` with `field(default_factory=dict)`.

#### TC-402: `_task_to_feature_context()` Unchanged

**Status:** planned (constraint, not code change)

The `_task_to_feature_context()` method in `context_seed_handlers.py` is not modified. Tier classification is purely a rendering concern, not a population concern.

**Acceptance criteria:**
1. No changes to `_task_to_feature_context()` in `context_seed_handlers.py`.
2. Field population logic and conditional guards remain identical.

#### TC-403: Design Prompt Templates Unchanged

**Status:** planned (constraint, not code change)

The `design.yaml` prompt templates are not modified. The `{additional_context}` placeholder continues to receive a string — the string is now structured rather than flat, but the template is unchanged.

**Acceptance criteria:**
1. No changes to `src/startd8/contractors/artisan_phases/prompts/design.yaml`.
2. The `{additional_context}` placeholder in `design_user` and `refine_user` templates is unchanged.

#### TC-404: T0/T1 Rendering Fidelity

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py`

For T0 and T1 fields, the rendered output must be character-identical to the current inline loop when no budget compression is applied. This ensures that existing test assertions and prompt behavior are preserved.

**Acceptance criteria:**
1. For a dict containing only T0/T1 string fields, `format_tiered_context()` output (after stripping section headers) matches the current inline loop output.
2. For a dict containing only T0/T1 non-string fields, `json.dumps(v, indent=2, default=str)` output is preserved.
3. The existing `test_nested_dict_preserved` test continues to pass (the field tested, if T0/T1, retains full JSON rendering).

#### TC-405: Unknown Fields Default to T2

**Status:** planned
**Source:** `src/startd8/contractors/prompt_utils.py`

Fields not present in `CONTEXT_FIELD_TIERS` are assigned tier 2 (Medium) by default. This ensures forward compatibility when new fields are added to `_task_to_feature_context()` — they receive collapsed rendering without requiring a registry update.

**Acceptance criteria:**
1. `CONTEXT_FIELD_TIERS.get(field_name, 2)` is used for tier lookup.
2. A field named `"new_unknown_field"` renders in the T2 section with collapsed formatting.
3. No `KeyError` or crash for unregistered field names.

---

### Layer 5: Test Coverage (TC-5xx)

#### TC-500: Empty Input Test

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. `format_tiered_context({})` returns `"None"`.
2. `format_tiered_context(None)` returns `"None"`.

#### TC-501: T0 Full Rendering Test

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. A T0 string field (e.g., `critical_parameters_checklist`) renders as `**critical_parameters_checklist:** <value>`.
2. The output contains `### Critical Context` header.
3. No truncation is applied regardless of string length.

#### TC-502: T1 Full Rendering Test

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. A T1 string field (e.g., `project_goals`) renders with bold key and full value.
2. A T1 list field (e.g., `constraints_from_manifest`) renders with `json.dumps(indent=2)`.
3. The output contains `### Design Constraints` header.

#### TC-503: T2 Collapsed Rendering Test

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. A T2 dict field with nested content shows top-level keys with `{...N items}` hints.
2. A T2 string field >300 chars is truncated with `[...N more chars]` suffix.
3. A T2 string field ≤300 chars is rendered in full.
4. A T2 list field shows count and first-item preview.
5. The output contains `### Supporting Information` header.

#### TC-504: T3 Metadata Line Test

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. Multiple T3 fields are rendered as a single pipe-delimited line.
2. The output contains `### Metadata` header.
3. Multi-line values are collapsed to first line.
4. Values exceeding 60 chars are truncated.

#### TC-505: Unknown Field Defaults to T2

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. A field not in `CONTEXT_FIELD_TIERS` appears in the `### Supporting Information` section.
2. It receives T2 collapsed rendering.

#### TC-506: Empty Tier Omission Test

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. When only T0 and T3 fields are present, `### Design Constraints` and `### Supporting Information` headers are absent.
2. Only non-empty tier sections appear in the output.

#### TC-507: Budget Compression — T3 Drop

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. With a very low `token_budget` (e.g., 100), T3 metadata is absent from output.
2. T0 fields are still present in full.

#### TC-508: Budget Compression — T2 Collapse

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. With a `token_budget` low enough to trigger T2 compression but not T1 truncation, T2 fields are re-rendered as one-liners.
2. T0 fields are still present in full.

#### TC-509: Budget Compression — T1 Truncation

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. With a `token_budget` of 50 (extreme), T1 string fields are truncated to 500 chars.
2. T0 fields are still present in full, untruncated.

#### TC-510: Backward Compatibility — Existing Test Preservation

**Status:** planned
**Source:** `tests/unit/contractors/test_tiered_context_rendering.py`

**Acceptance criteria:**
1. A dict with `shared_modules` (T1) containing nested values preserves full JSON rendering under normal budget — validates that existing `test_nested_dict_preserved` semantics hold.

---

## 5. Data Flow Diagram

```
_task_to_feature_context()          format_tiered_context()            design.yaml
(context_seed_handlers.py)          (prompt_utils.py)                  template
         │                                   │                            │
         │  additional_context: dict          │                            │
         ├──────────────────────────────────▸ │                            │
         │                                   │                            │
         │                          ┌────────┴────────┐                   │
         │                          │ CONTEXT_FIELD_   │                   │
         │                          │ TIERS registry   │                   │
         │                          │ (TC-100)         │                   │
         │                          └────────┬────────┘                   │
         │                                   │                            │
         │                          ┌────────┴────────┐                   │
         │                          │ Group by tier    │                   │
         │                          │ T0 → _render_full│                   │
         │                          │ T1 → _render_full│                   │
         │                          │ T2 → _render_    │                   │
         │                          │      collapsed   │                   │
         │                          │ T3 → _render_    │                   │
         │                          │      metadata    │                   │
         │                          └────────┬────────┘                   │
         │                                   │                            │
         │                          ┌────────┴────────┐                   │
         │                          │ Token budget     │                   │
         │                          │ check (TC-200)   │                   │
         │                          │                  │                   │
         │                          │ Over? → compress │                   │
         │                          │ 1. Drop T3       │                   │
         │                          │ 2. Collapse T2   │                   │
         │                          │ 3. Truncate T1   │                   │
         │                          └────────┬────────┘                   │
         │                                   │                            │
         │                          additional_context_str                │
         │                                   │                            │
         │                                   ├──────────────────────────▸ │
         │                                   │     {additional_context}   │
         │                                   │     placeholder           │
```

### Compression cascade

```
Initial render (all tiers)
        │
        ▼
 est_tokens = len(output) // 4
        │
        ├── ≤ budget → done (no compression)
        │
        ▼
 Drop T3 section
        │
        ├── ≤ budget → done
        │
        ▼
 Re-render T2 as one-liners
        │
        ├── ≤ budget → done
        │
        ▼
 Truncate T1 strings to 500 chars
        │
        └── done (final state; T0 untouched)
```

---

## 6. Traceability Matrix

### Source Files → Requirements

| Source File | Requirements |
|-------------|-------------|
| `src/startd8/contractors/prompt_utils.py` | TC-100, TC-101, TC-102, TC-103, TC-104, TC-200, TC-201, TC-202, TC-203, TC-400, TC-404, TC-405 |
| `src/startd8/contractors/artisan_phases/design_documentation.py` | TC-300 |
| `src/startd8/contractors/artisan_phases/prompts/__init__.py` | TC-301 |

### Constraint Requirements (no code changes)

| Constraint | Files Protected |
|-----------|----------------|
| TC-401 (FeatureContext unchanged) | `design_documentation.py` (`FeatureContext` dataclass) |
| TC-402 (`_task_to_feature_context` unchanged) | `context_seed_handlers.py` |
| TC-403 (design.yaml unchanged) | `prompts/design.yaml` |

### Test Files → Requirements

| Test File | Requirements Verified |
|-----------|----------------------|
| `tests/unit/contractors/test_tiered_context_rendering.py` | TC-500, TC-501, TC-502, TC-503, TC-504, TC-505, TC-506, TC-507, TC-508, TC-509, TC-510 |

### Upstream Requirements (extends)

| This Requirement | Extends | Relationship |
|-----------------|---------|-------------|
| TC-300 | AR-300 (design generation) | Replaces inline context formatting in design generation |
| TC-100 | CCD-201 (two-tier context model) | Extends two-tier to four-tier classification |
| TC-200 | Lane-peer token budget (`_apply_lane_peer_token_budget`) | Reuses same `chars // 4` token estimation |

---

## 7. Status Dashboard

| Layer | ID Range | Total | Implemented | Planned |
|-------|----------|-------|-------------|---------|
| Tier Registry & Entry Point | TC-1xx | 5 | 0 | 5 |
| Token Budget & Compression | TC-2xx | 4 | 0 | 4 |
| Integration | TC-3xx | 2 | 0 | 2 |
| Backward Compatibility | TC-4xx | 6 | 0 | 6 |
| Test Coverage | TC-5xx | 11 | 0 | 11 |
| **Total** | | **28** | **0** | **28** |

> **ID scheme:** TC-1xx (100-104) = 5, TC-2xx (200-203) = 4, TC-3xx (300-301) = 2, TC-4xx (400-405) = 6, TC-5xx (500-510) = 11. Total = 28. Gaps between IDs within a layer are reserved for future use.

---

## 8. Verification

### Unit Tests

```bash
python3 -m pytest tests/unit/contractors/test_tiered_context_rendering.py -v
```

### Existing Test Regression

```bash
# Verify no regression in existing design phase tests
python3 -m pytest tests/unit/contractors/ -v -k "design"
```

### Manual Prompt Inspection

1. **Before/after comparison:** Run a design phase with logging enabled and compare the `additional_context` portion of the user prompt before and after the change.

2. **Token savings measurement:** For a typical manifest-rich task, measure:
   - Current: `len(additional_context_str) // 4` tokens
   - After: `len(format_tiered_context(additional_context)) // 4` tokens
   - Expected reduction: 30-50% for typical tasks, 50-70% for maximum tasks

3. **Tier header verification:** Confirm the LLM-facing prompt contains section headers (`### Critical Context`, `### Design Constraints`, etc.) that create navigable structure.

4. **Budget compression verification:** Set `token_budget=500` and verify T3 is dropped and T2 is collapsed, while T0 fields remain intact.

---

## 9. Related Documents

| Document | Relationship |
|----------|-------------|
| `ARTISAN_REQUIREMENTS.md` | Parent — AR-300 (design generation) is extended |
| `CONTEXT_CORRECTNESS_BY_DESIGN_REQUIREMENTS.md` | Sibling — CCD-201 (two-tier context model) is extended to four tiers |
| `ARTISAN_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md` | Sibling — format reference for this document |
| `MOTTAINAI_DESIGN_PRINCIPLE.md` | Design principle — Rule 2 (forward, don't regenerate) and Rule 6 (measure the gap) |
| `ARTISAN_PROMPT_EXTERNALIZATION_REQUIREMENTS.md` | Sibling — prompt template externalization pattern |
| `PROJECT_CENTRIC_ARTISAN_REQUIREMENTS.md` | Sibling — project-centric context enrichment feeds into additional_context |
