# Artisan Prompt Externalization and Quality Improvements — Requirements

**Version:** 1.1.0
**Created:** 2026-02-20
**Updated:** 2026-02-21
**Implements:** IMP-1 through IMP-9 (IMP-1–7 from Online Boutique regeneration defect analysis; IMP-8–9 from REFINE output forwarding)

---

## Overview

Runs 1–2 of the Online Boutique regeneration produced 11 defects, 9 caused by information loss at PARSE/DESIGN bottlenecks. This document specifies (a) the externalization of all 22 artisan pipeline prompts from Python source into YAML configuration files, and (b) 7 targeted improvements to the prompt content and data flow to eliminate those defects.

### Motivation

Hardcoded prompt strings in Python source create three problems:

1. **Opaque to non-engineers.** Prompt text buried in multi-hundred-line `.py` files is invisible to reviewers who want to inspect or tune LLM behavior.
2. **Coupled to code releases.** Changing a single word in a prompt requires a Python code change, test run, and release cycle.
3. **Difficult to audit.** Grepping for all prompt text across 4 source modules is error-prone; a single YAML-per-phase structure makes the full prompt corpus scannable.

### Status

| Requirement | Status |
|-------------|--------|
| REQ-PE-001 YAML storage | Implemented |
| REQ-PE-002 Loader module | Implemented |
| REQ-PE-003 Package data | Implemented |
| REQ-PE-004 Backward compatibility | Implemented |
| IMP-1 Requirements text | Implemented |
| IMP-2 Protocol guidance | Implemented |
| IMP-3 All target_files | Implemented |
| IMP-4 ParsedFeature schema | Implemented |
| IMP-5 Constraint tagging | Implemented |
| IMP-6 Critical parameters | Implemented |
| IMP-7 Validation gate | Implemented |
| IMP-8 Structured refine suggestions | Implemented |
| IMP-9 REFINE compliance in REVIEW | Implemented |

---

## Part A: Prompt Externalization

### REQ-PE-001: YAML Prompt Storage

All artisan pipeline prompt templates MUST be stored as YAML files in `src/startd8/contractors/artisan_phases/prompts/`, one file per source module:

| File | Source Module | Prompt Count |
|------|-------------|-------------|
| `design.yaml` | `design_documentation.py` | 12 |
| `plan_ingestion.yaml` | `plan_ingestion_workflow.py` | 4 + depth_tiers |
| `test_construction.yaml` | `test_construction.py` | 4 |
| `review.yaml` | `context_seed_handlers.py` | 2 |

#### YAML Structure

Each file follows this schema:

```yaml
prompts:
  <prompt_name>:
    description: "<human-readable purpose>"
    template: |
      <prompt text with {placeholder} syntax>
    placeholders: [<list of placeholder names>]
```

- The `template` field contains the full prompt text with `{placeholder}` syntax compatible with Python `str.format()`.
- The `placeholders` field is documentation-only — not enforced by the loader.
- YAML block scalars (`|`) preserve literal newlines. A trailing newline is acceptable for LLM prompts.
- Curly braces that should appear literally in the output (e.g., JSON schema examples) MUST be doubled (`{{`, `}}`) for `str.format()` compatibility.

#### Depth Tiers

`plan_ingestion.yaml` also contains a `depth_tiers` top-level key with calibration tiers (`brief`, `standard`, `comprehensive`), each specifying `max_tokens` and `sections`.

### REQ-PE-002: Loader Module

The prompt loader MUST be implemented as `src/startd8/contractors/artisan_phases/prompts/__init__.py` with the following public API:

| Function | Signature | Purpose |
|----------|-----------|---------|
| `get_template` | `(phase: str, prompt_name: str) -> str` | Return raw template with `{placeholders}` intact |
| `format_prompt` | `(phase: str, prompt_name: str, **kwargs) -> str` | Return filled prompt |
| `get_depth_tiers` | `() -> dict[str, dict[str, Any]]` | Return depth tier configuration |
| `format_constraints` | `(constraints: list[str]) -> str` | Group constraints by priority prefix (IMP-5) |

Implementation requirements:
- Use `functools.lru_cache` on `_load_file()` to avoid repeated disk I/O.
- Use `Path(__file__).parent` for file resolution (matches existing SDK patterns).
- Raise `FileNotFoundError` for missing YAML files and `KeyError` for missing prompt names.

### REQ-PE-003: Package Data

`pyproject.toml` MUST include `"contractors/artisan_phases/prompts/*.yaml"` in the `[tool.setuptools.package-data]` section so YAML files are distributed with the package.

### REQ-PE-004: Backward Compatibility

- `build_design_system_prompt()` and `build_refine_system_prompt()` MUST continue to accept `sections` and `depth_guidance` parameters and return formatted strings — but load their base template from YAML internally.
- `DESIGN_GENERATION_SYSTEM_PROMPT` MUST remain as a module-level constant (calling `build_design_system_prompt()` with defaults).
- Existing test suites MUST pass without modification (beyond `FakeSeedTask` field additions).

---

## Part B: Quality Improvements (IMP-1 through IMP-9)

### IMP-1: Requirements Text in DESIGN Prompt

**Defect:** Verbatim requirements text (parameter values, specific configurations) was lost between plan ingestion and DESIGN prompt, causing the design to omit or generalize critical details.

**Requirements:**
- `SeedTask` MUST have a `requirements_text: str` field populated from `config.requirements_text` in `from_seed_entry()`.
- `FeatureContext` MUST have a `requirements_text: str` field, set from `task.requirements_text` in `_task_to_feature_context()`.
- The `design_user` YAML template MUST include a `{requirements_block}` placeholder.
- When `requirements_text` is non-empty, it MUST be formatted as: `**Requirements (verbatim — authoritative for parameter details):**\n{text}`
- When empty, the block MUST be omitted (empty string).

### IMP-2: Protocol-Aware DESIGN System Prompt

**Defect:** Design documents prescribed wrong health check types (e.g., HTTP `curl` for gRPC services) because the system prompt had no protocol guidance.

**Requirements:**
- The `design_system` YAML template MUST include a "Protocol and Parameter Fidelity" section with guidance for:
  - HEALTHCHECK type matching transport protocol (gRPC → `grpc_health_probe`, HTTP → `curl`)
  - `transport_protocol` from `service_metadata` as authoritative
  - Verbatim parameter value preservation from requirements
  - Explicit negative scope statements (e.g., "no OpenTelemetry")

### IMP-3: All target_files Passed to DESIGN

**Defect:** `_task_to_feature_context()` passed only `target_files[0]` to `FeatureContext.target_file`, losing multi-file context.

**Requirements:**
- `_task_to_feature_context()` MUST use `", ".join(task.target_files)` instead of `task.target_files[0]`.

### IMP-4: ParsedFeature Schema Expansion

**Defect:** Plan ingestion parsed feature descriptions but lost structured metadata (API signatures, protocol, dependencies, negative scope) that downstream phases need.

**Requirements:**
- `ParsedFeature` MUST have 4 new fields: `api_signatures: List[str]`, `protocol: str`, `runtime_dependencies: List[str]`, `negative_scope: List[str]`.
- `SeedTask` MUST have matching fields, populated from `from_seed_entry()`.
- The `parse` prompt in `plan_ingestion.yaml` MUST instruct the LLM to extract these 4 fields.
- `to_seed_dict()` MUST include all 4 fields in the output.

### IMP-5: Constraint Priority Tagging

**Defect:** All constraints were presented as a flat list, making it unclear which were hard requirements vs. preferences. LLMs occasionally violated binding constraints.

**Requirements:**
- Constraint strings MUST use prefix tags: `[BINDING]`, `[STRUCTURAL]`, `[ADVISORY]`.
- `format_constraints()` in the prompt loader MUST group constraints by tag into sections:
  - `### Binding (must not violate)` — constraints prefixed with `[BINDING]`
  - `### Structural (code organization)` — constraints prefixed with `[STRUCTURAL]`
  - `### Advisory (prefer but not blocking)` — constraints prefixed with `[ADVISORY]`
  - Untagged constraints rendered as flat bullet list
- Empty constraint lists MUST return empty string.
- Preflight rules in `rules_python_single.py` MUST tag their constraint strings.

### IMP-6: Critical Parameters Elevation

**Defect:** `resolved_parameters` were buried in the flat `additional_context` dict and ignored by the LLM during design generation.

**Requirements:**
- `_generate_design()` MUST extract `resolved_parameters` and `parameter_sources` from `additional_context` when non-empty.
- These MUST be formatted as a dedicated section: `**Critical Parameters (from requirements — include verbatim in design):**`
- The section MUST be prepended before the general additional context to ensure visibility.

### IMP-7: DESIGN to IMPLEMENT Validation Gate

**Defect:** Resolved parameters that were specified in requirements but absent from the design document were silently lost, causing the implementation to omit them.

**Requirements:**
- After design generation and before chunk creation, the system MUST scan the design document text for each resolved parameter's key value.
- Missing parameters MUST be recorded as a `design_completeness_warning` string in chunk metadata.
- `_build_task_description()` in `LeadContractorChunkExecutor` MUST inject a `## Design Completeness Warning` section when the warning is non-empty.
- When the warning is empty, no section MUST be injected.

### IMP-8: Structured Refine Suggestions in DESIGN

**Defect:** REFINE output forwarding (REQ-RF-001–012) now places structured triage decisions in `seed.onboarding.refine_suggestions` — a list of dicts with `id`, `decision`, `rationale`, `area`, `severity`. However, the DESIGN phase handler consumes refine suggestions exclusively through a **text-based path**: artifact inventory lookup (`lookup_artifact(inventory, "refine_suggestions")` → string) or plan document fallback (`inv_plan_document` → full Appendix C text), parsed by `_extract_task_suggestions()` which scans for `S-`/`F-` prefixed lines. The structured data is richer (pre-filtered to ACCEPT only, includes acceptance rationale and severity) but has no consumer.

Additionally, the `design_system` YAML template contains no guidance on how to use refine suggestions when they appear in `{additional_context}`. They arrive as one of 20+ opaque key-value entries with no signal that they represent pre-triaged, accepted architectural review feedback that should take priority over general context.

**Prerequisite:** REQ-RF-001–006 (REFINE output forwarding) — implemented.

**Requirements:**

#### IMP-8a: Structured data extraction in DesignPhaseHandler

- `DesignPhaseHandler.execute()` MUST extract `onboarding.refine_suggestions` from the seed (via `context.get("onboarding_refine_suggestions")`) as a `List[Dict[str, Any]]`.
- When this structured data is non-empty, `_task_to_feature_context()` MUST format it as a markdown section and inject into `additional_context["refine_suggestions"]`, replacing the text-based extraction for that task.
- Format: one bullet per accepted suggestion — `- **[{severity}] {area}** ({id}): {rationale}`
- When the structured data is empty or absent, the existing text-based path (artifact inventory → `_extract_task_suggestions()`) MUST remain as fallback for backward compatibility.

#### IMP-8b: Seed extraction and checkpoint persistence

- `_build_initial_context()` in `context_seed_handlers.py` MUST extract `onboarding.refine_suggestions` into `context["onboarding_refine_suggestions"]` (following the PCA-201 pattern at lines 654–671).
- `_CHECKPOINT_CONTEXT_KEYS` in `artisan_contractor.py` MUST include `"onboarding_refine_suggestions"` so the structured data survives checkpoint resume.

#### IMP-8c: DESIGN system prompt guidance

- The `design_system` YAML template MUST include guidance in the `Rules:` section:
  ```
  - When refine_suggestions appear in Additional Context, they contain accepted
    architectural review feedback from the REFINE phase. These have been triaged
    and approved — incorporate them into your design rather than contradicting or
    ignoring them. Each suggestion includes an area and severity to guide priority.
  ```
- The `refine_system` template MUST include equivalent guidance in its `Rules:` section, emphasizing that the refinement should address accepted suggestions rather than discarding them.

### IMP-9: REFINE Compliance in REVIEW Prompt

**Defect:** REFINE output forwarding places apply provenance in `seed.artifacts.refine_provenance` — including `applied_ids` (suggestion IDs integrated into the plan document body), `triage_accepted`/`triage_rejected` counts, and `warning_ids`. The REVIEW phase has no awareness of these accepted suggestions. It evaluates code against the design document and constraints but cannot verify that architectural review suggestions were properly reflected in the implementation.

The REVIEW prompt already injects contextual sections (design compliance, parameter sources, semantic conventions, truncation warnings) before `## Review Instructions` using `prompt.replace()`. REFINE compliance fits this established pattern.

**Prerequisite:** REQ-RF-004–006 (seed injection) — implemented.

**Requirements:**

#### IMP-9a: Refine provenance extraction

- `ReviewPhaseHandler._review_single_task()` MUST read `refine_provenance` from the context (extracted from `seed.artifacts.refine_provenance` during seed loading).
- The provenance dict MUST be passed to `_build_review_prompt()` as a new optional parameter: `refine_provenance: dict[str, Any] | None = None`.

#### IMP-9b: REFINE compliance section injection

- `_build_review_prompt()` MUST inject a `## REFINE Compliance` section before `## Review Instructions` when `refine_provenance` is present and `applied_ids` is non-empty.
- The section MUST contain:
  - The count of accepted suggestions that were applied to the plan document.
  - The list of applied suggestion IDs.
  - An instruction: *"These architectural suggestions were accepted during plan refinement and integrated into the design document. Verify the implementation reflects them. Score lower if accepted suggestions are contradicted by the implementation."*
- When `applied_ids` is empty or `refine_provenance` is absent, no section MUST be injected.
- The section MUST be truncated to 1500 chars maximum (consistent with other injected sections).

#### IMP-9c: Checkpoint persistence

- `_CHECKPOINT_CONTEXT_KEYS` in `artisan_contractor.py` MUST include `"refine_provenance"` so the provenance data survives checkpoint resume.
- `_build_initial_context()` MUST extract `seed.artifacts.refine_provenance` into `context["refine_provenance"]`.

#### IMP-9d: `review.yaml` documentation

- The `review_user` prompt `placeholders` list in `review.yaml` MUST document that a `## REFINE Compliance` section may be injected dynamically (matching existing documentation pattern for design compliance and truncation warning sections).

---

## Files Modified

### IMP-1 through IMP-7 (Implemented)

| File | Changes |
|------|---------|
| `src/startd8/contractors/artisan_phases/prompts/__init__.py` | NEW — loader + constraint formatter |
| `src/startd8/contractors/artisan_phases/prompts/design.yaml` | NEW — 12 prompts |
| `src/startd8/contractors/artisan_phases/prompts/plan_ingestion.yaml` | NEW — 4 prompts + depth tiers |
| `src/startd8/contractors/artisan_phases/prompts/test_construction.yaml` | NEW — 4 prompts |
| `src/startd8/contractors/artisan_phases/prompts/review.yaml` | NEW — 2 prompts |
| `src/startd8/contractors/artisan_phases/design_documentation.py` | YAML loading, FeatureContext.requirements_text, IMP-6 |
| `src/startd8/contractors/context_seed_handlers.py` | SeedTask fields, IMP-1/3/4, review prompts, IMP-7 gate |
| `src/startd8/contractors/artisan_phases/development.py` | IMP-5 formatting, IMP-7 warning injection |
| `src/startd8/contractors/artisan_phases/test_construction.py` | YAML loading |
| `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | YAML loading, depth tiers |
| `src/startd8/workflows/builtin/plan_ingestion_models.py` | IMP-4 ParsedFeature fields |
| `src/startd8/workflows/builtin/preflight_rules/rules_python_single.py` | IMP-5 constraint tags |
| `pyproject.toml` | Package data for YAML files |
| `tests/unit/contractors/conftest.py` | FakeSeedTask new fields |
| `tests/unit/contractors/test_artisan_prompt_improvements.py` | NEW — 32 tests |

### IMP-8 and IMP-9 (Implemented)

| File | Changes |
|------|---------|
| `src/startd8/contractors/context_seed_handlers.py` | IMP-8a: structured refine_suggestions extraction in `_task_to_feature_context()` + `DesignPhaseHandler.execute()`. IMP-8b: `onboarding_refine_suggestions` extraction in `_build_initial_context()`. IMP-9a: `refine_provenance` extraction + passthrough to `_build_review_prompt()` |
| `src/startd8/contractors/artisan_contractor.py` | IMP-8b/9c: add `onboarding_refine_suggestions` and `refine_provenance` to `_CHECKPOINT_CONTEXT_KEYS` |
| `src/startd8/contractors/artisan_phases/prompts/design.yaml` | IMP-8c: refine suggestions guidance in `design_system` and `refine_system` Rules sections |
| `src/startd8/contractors/artisan_phases/prompts/review.yaml` | IMP-9d: document dynamic `## REFINE Compliance` section in `review_user` placeholders |

## Verification

### IMP-1 through IMP-7

- 32/32 new tests pass (`test_artisan_prompt_improvements.py`)
- 1194/1195 contractor regression tests pass (1 pre-existing failure unrelated to these changes)

### IMP-8 and IMP-9 (Implemented)

- Structured extraction: test that `onboarding_refine_suggestions` from seed overrides text-based path, with fallback when absent
- Prompt content: test that `design_system` formatted prompt contains refine suggestions guidance text
- REVIEW compliance: test that `_build_review_prompt()` injects `## REFINE Compliance` section when `applied_ids` non-empty, omits when empty
- Checkpoint: test that `_CHECKPOINT_CONTEXT_KEYS` includes both new keys and that checkpoint round-trip preserves them
- Backward compat: test that text-based refine path still works when structured data absent (old seeds)
