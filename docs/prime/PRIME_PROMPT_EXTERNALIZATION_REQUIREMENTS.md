# Prime Contractor Prompt Externalization — Requirements

**Version:** 1.0.0
**Created:** 2026-02-20
**Pattern:** Follows `docs/artisan/ARTISAN_PROMPT_EXTERNALIZATION_REQUIREMENTS.md` (REQ-PE-001 through REQ-PE-004)

---

## Overview

The prime contractor route (PrimeContractorWorkflow + LeadContractorWorkflow) contains 11 prompt fragments spread across 3 source files, all hardcoded as Python string constants or inline f-strings. This document specifies (a) externalization of all 11 prompts into YAML configuration files, and (b) 6 targeted improvements to prompt content and context flow, informed by the same defect analysis that drove the artisan improvements.

### Motivation

The artisan route's prompt externalization (REQ-PE-001 through REQ-PE-004, now implemented) proved three benefits:

1. **Visibility** — YAML files are scannable and auditable without reading Python source.
2. **Decoupled iteration** — Prompt text can be edited, reviewed, and versioned independently of code logic.
3. **Consistency** — A single loader module (`artisan_phases/prompts/__init__.py`) eliminates ad-hoc template formatting.

The prime route has the same three problems: 11 prompts are buried in 3 Python files totaling ~1,250 lines, prompt edits require code changes, and there is no consistent formatting API.

### Prompt Inventory

| # | Prompt | Location | Type | Lines |
|---|--------|----------|------|-------|
| 1 | `SPEC_PROMPT_TEMPLATE` | `lead_contractor_workflow.py:76-128` | System+User combined | 52 |
| 2 | `DRAFT_PROMPT_TEMPLATE` | `lead_contractor_workflow.py:130-155` | User prompt | 25 |
| 3 | `SINGLE_FILE_OUTPUT_FORMAT` | `lead_contractor_workflow.py:158-162` | Output format fragment | 5 |
| 4 | `MULTI_FILE_OUTPUT_FORMAT` | `lead_contractor_workflow.py:164-202` | Output format fragment | 39 |
| 5 | `REVIEW_PROMPT_TEMPLATE` | `lead_contractor_workflow.py:228-264` | User prompt | 37 |
| 6 | `INTEGRATION_PROMPT_TEMPLATE` | `lead_contractor_workflow.py:266-295` | User prompt | 30 |
| 7 | File manifest injection | `lead_contractor_workflow.py:856-872` | Dynamic context | 17 |
| 8 | `output_constraint` | `prime_contractor.py:440` | Inline string | 1 |
| 9 | `prior_error_feedback` | `prime_contractor.py:473` | Inline string | 1 |
| 10 | Multi-file retry feedback | `generators/lead_contractor.py:257-279` | Inline f-string | 23 |
| 11 | Per-file role hints | `generators/lead_contractor.py:242-255` | Dynamic builder | 14 |

**Total:** 11 prompt fragments, ~244 lines of prompt text across 3 files.

### Context Flow (Current State)

```
Context Seed (JSON)
  ↓
run_prime_workflow.py — stashes seed-level context on PrimeContractorWorkflow
  ↓
PrimeContractorWorkflow._generate_code() — builds gen_context dict (10+ keys):
  feature_name, target_file, domain_constraints, output_constraint,
  project_objectives, semantic_conventions, architectural_context,
  implement_max_output_tokens, plan_context, prior_error_feedback
  ↓
LeadContractorCodeGenerator.generate() — wraps gen_context, calls workflow
  ↓
LeadContractorWorkflow._create_spec()
  → SPEC_PROMPT_TEMPLATE.format(task_description, context=JSON.dumps(gen_context), domain_constraints)
  → Lead agent produces ImplementationSpec
  ↓
LeadContractorWorkflow._create_draft()
  → DRAFT_PROMPT_TEMPLATE.format(spec=raw_spec, feedback, output_format)
  → Drafter agent produces code
  ↓
LeadContractorWorkflow._review_draft()
  → REVIEW_PROMPT_TEMPLATE.format(task_description, spec, implementation, pass_threshold)
  → Lead agent reviews
  ↓
LeadContractorWorkflow._integrate_final()
  → INTEGRATION_PROMPT_TEMPLATE.format(task_description, implementation, review_history, integration_instructions)
  → Lead agent finalizes
```

### Information Loss Points

The prime route has analogous loss points to the artisan route:

| Loss Point | Location | Mechanism |
|-----------|----------|-----------|
| **LP-P1: Context flattening** | `_create_spec()` line 852 | `json.dumps(context)` serializes 10+ keys into a flat JSON blob. The lead architect sees no structure or priority. Enrichment data (resolved_parameters, semantic_conventions) is buried alongside feature_name and output_constraint. |
| **LP-P2: No requirements text** | `_generate_code()` line 474 | `task=feature.description` passes only the compressed single-line description from plan ingestion. Verbatim requirements text is not available. |
| **LP-P3: Constraint dilution** | `_create_spec()` lines 845-850 | Domain constraints are formatted as a flat bulleted list with no priority distinction. Binding constraints mixed with advisory. |
| **LP-P4: No protocol awareness** | SPEC_PROMPT_TEMPLATE | No guidance about protocol-sensitive decisions (HEALTHCHECK type, gRPC vs HTTP clients, OTel scope). The lead architect must infer from the task description. |
| **LP-P5: No spec-to-draft validation** | Between _create_spec and _create_draft | If the spec drops a critical parameter, the drafter faithfully implements the incomplete spec. No safety net. |

---

## Part A: Prompt Externalization

### REQ-PPE-001: YAML Prompt Storage

All prime contractor prompt templates MUST be stored as YAML files in `src/startd8/workflows/builtin/prompts/`, one file per source module:

| File | Source Module | Prompt Count |
|------|--------------|-------------|
| `lead_contractor.yaml` | `lead_contractor_workflow.py` | 6 (spec, draft, single_file_output, multi_file_output, review, integration) |
| `prime_context.yaml` | `prime_contractor.py` + `generators/lead_contractor.py` | 5 (output_constraint, prior_error_feedback, file_manifest, multi_file_retry, role_hints) |

#### YAML Structure

Each file follows the same schema as the artisan prompts:

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
- YAML block scalars (`|`) preserve literal newlines.
- Curly braces that should appear literally (e.g., JSON examples) MUST be doubled (`{{`, `}}`) for `str.format()` compatibility.

#### Prompt Names

**`lead_contractor.yaml`:**

| Prompt Name | Current Constant | Purpose |
|-------------|-----------------|---------|
| `spec` | `SPEC_PROMPT_TEMPLATE` | Lead creates implementation specification |
| `draft` | `DRAFT_PROMPT_TEMPLATE` | Drafter implements from spec |
| `single_file_output` | `SINGLE_FILE_OUTPUT_FORMAT` | Output format for single-file tasks |
| `multi_file_output` | `MULTI_FILE_OUTPUT_FORMAT` | Output format for multi-file tasks |
| `review` | `REVIEW_PROMPT_TEMPLATE` | Lead reviews draft implementation |
| `integration` | `INTEGRATION_PROMPT_TEMPLATE` | Lead finalizes implementation |

**`prime_context.yaml`:**

| Prompt Name | Current Location | Purpose |
|-------------|-----------------|---------|
| `output_constraint` | `prime_contractor.py:440` | Single-module constraint when no domain enrichment |
| `prior_error_feedback` | `prime_contractor.py:473` | Error-informed retry guidance |
| `file_manifest` | `lead_contractor_workflow.py:856-872` | Multi-file manifest injected into context |
| `multi_file_retry` | `generators/lead_contractor.py:257-279` | Retry feedback when multi-file split fails |
| `role_hints` | `generators/lead_contractor.py:242-255` | Per-file role descriptions for retry |

### REQ-PPE-002: Loader Module

The prime prompt loader MUST be implemented as `src/startd8/workflows/builtin/prompts/__init__.py` with a public API matching the artisan loader pattern:

| Function | Signature | Purpose |
|----------|-----------|---------|
| `get_template` | `(phase: str, prompt_name: str) -> str` | Return raw template with `{placeholders}` intact |
| `format_prompt` | `(phase: str, prompt_name: str, **kwargs) -> str` | Return filled prompt |

Implementation requirements:
- Use `functools.lru_cache` on `_load_file()` to avoid repeated disk I/O.
- Use `Path(__file__).parent` for file resolution.
- Raise `FileNotFoundError` for missing YAML files and `KeyError` for missing prompt names.
- Phase names map to YAML file stems: `"lead_contractor"` → `lead_contractor.yaml`, `"prime_context"` → `prime_context.yaml`.

### REQ-PPE-003: Package Data

`pyproject.toml` MUST include `"workflows/builtin/prompts/*.yaml"` in the `[tool.setuptools.package-data]` section so YAML files are distributed with the package.

### REQ-PPE-004: Backward Compatibility

- `SPEC_PROMPT_TEMPLATE`, `DRAFT_PROMPT_TEMPLATE`, `REVIEW_PROMPT_TEMPLATE`, and `INTEGRATION_PROMPT_TEMPLATE` MUST remain as module-level constants in `lead_contractor_workflow.py`, but their values MUST be loaded from YAML at import time.
- `SINGLE_FILE_OUTPUT_FORMAT` and `MULTI_FILE_OUTPUT_FORMAT` MUST remain as module-level constants, loaded from YAML.
- `_build_output_format()` MUST continue to work as before, using the YAML-loaded constants.
- Existing test suites MUST pass without modification.

---

## Part B: Quality Improvements (IMP-P1 through IMP-P6)

These improvements address the same class of defects found in Runs 1-2 of the Online Boutique regeneration but for the prime route. The artisan route's IMP-1 through IMP-7 are now implemented; these are the prime-route equivalents.

### IMP-P1: Structured Context in Spec Prompt

**Loss Point:** LP-P1 (context flattening)
**Defects prevented:** All context-dilution defects where the lead architect overlooked critical parameters buried in a JSON blob.

**Problem:** `_create_spec()` serializes the entire `gen_context` dict via `json.dumps(context, indent=2)` and injects it into a single `{context}` placeholder. The lead architect receives:
```
## Context
{
  "feature_name": "PI-008",
  "target_file": "src/shoppingassistantservice/shoppingassistantservice.py",
  "project_objectives": { ... },
  "semantic_conventions": { ... },
  "architectural_context": { ... },
  "plan_context": "... 60KB of plan text ...",
  "domain_constraints": [ ... ]
}
```

Critical parameters are lost in this flat structure.

**Requirements:**
- `_create_spec()` MUST format context into dedicated sections rather than a flat JSON dump.
- The spec prompt template MUST include separate placeholders for structured context:
  ```
  ## Context
  {general_context}

  ## Project Architecture
  {architectural_context}

  ## Requirements (from plan — authoritative for parameter details)
  {requirements_context}

  ## Domain Constraints
  {domain_constraints}
  ```
- When `architectural_context` is empty, the section MUST be omitted.
- When `plan_context` is present, it MUST be formatted as a separate "Plan Context" section with length capped at the current 60KB limit.
- The `project_objectives` and `semantic_conventions` fields MUST be formatted as bullet lists, not raw JSON.

### IMP-P2: Requirements Text Passthrough

**Loss Point:** LP-P2 (no requirements text)
**Defects prevented:** DEV-R2-002, DEV-R2-004, DEV-R2-005 (parameters lost in description compression)

**Problem:** `PrimeContractorWorkflow._generate_code()` passes `task=feature.description` to the code generator. The `description` field is the compressed single-line summary from plan ingestion. The verbatim requirements text with parameter values, API signatures, and exact configurations is not passed through.

**Requirements:**
- `FeatureSpec` MUST support a `requirements_text` field (stored in metadata or as a direct field).
- `FeatureQueue.add_features_from_seed()` MUST populate `requirements_text` from `seed_task.requirements_text` when available.
- `PrimeContractorWorkflow._generate_code()` MUST include `requirements_text` in `gen_context` when non-empty.
- The spec prompt template MUST include a dedicated `{requirements_text}` section:
  ```
  ## Requirements (verbatim — authoritative for parameter details)
  {requirements_text}

  ## Task Description (summary)
  {task_description}
  ```
- When `requirements_text` is empty, the Requirements section MUST be omitted.

**Dependency:** This requires `requirements_text` to be populated in the context seed during plan ingestion. The artisan route's IMP-1 (now implemented) populates `requirements_text` on `SeedTask`. The prime route consumes this via `add_features_from_seed()`.

### IMP-P3: Critical Parameter Elevation

**Loss Point:** LP-P1 (enrichment data buried in context)
**Defects prevented:** DEV-R2-002, DEV-R2-004, DEV-R2-005

**Problem:** Enrichment data (`resolved_parameters`, `parameter_sources`) flows into the prime route through two paths:
1. `domain_constraints` list (from DomainChecklist enrichment)
2. `feature.metadata._enrichment.prompt_constraints` (from per-task metadata)

In both cases, resolved parameters are constraint strings in a flat list. The lead architect has no visual distinction between structural constraints ("define utility functions before classes") and critical parameters ("user='postgres'", "embedding_service=GoogleGenerativeAIEmbeddings").

**Requirements:**
- When `gen_context` contains enrichment data with `resolved_parameters` or `parameter_sources`, these MUST be extracted and formatted as a dedicated section in the spec prompt.
- The spec prompt template MUST include a `{critical_parameters}` placeholder:
  ```
  ## Critical Parameters (from requirements — include verbatim in spec)
  {critical_parameters}
  ```
- When no critical parameters are present, the section MUST be omitted.
- The extraction logic SHOULD reuse the same pattern as the artisan's IMP-6 in `design_documentation.py`.

### IMP-P4: Protocol-Aware Spec Guidance

**Loss Point:** LP-P4 (no protocol awareness)
**Defects prevented:** DEV-R2-001, DEV-001, DEV-004 (protocol mismatch defects)

**Problem:** The SPEC_PROMPT_TEMPLATE says "Be explicit, thorough, and leave no ambiguity" but gives no guidance on protocol-sensitive decisions. The lead architect must infer from the task description whether a service is gRPC, HTTP, or client-only, and make correct decisions about HEALTHCHECK type, client libraries, and instrumentation.

**Requirements:**
- The spec prompt template MUST include a "Protocol and Implementation Guidance" section:
  ```
  ## Protocol and Implementation Guidance
  - When designing Dockerfiles or health checks, HEALTHCHECK type MUST match transport
    protocol: gRPC → grpc_health_probe, HTTP → curl or omit, client-only → omit.
  - If context specifies transport_protocol, use it as authoritative.
  - When requirements specify exact parameter values (user="postgres", specific model names,
    system packages), carry these verbatim into the spec. Do not generalize.
  - When a service explicitly does NOT use a capability (e.g., "no OpenTelemetry"),
    state this in the spec so the drafter does not add it.
  ```
- This guidance MUST be in the spec prompt (not just the review prompt), because the spec is the primary control document for the drafter.

### IMP-P5: Constraint Categorization in Spec

**Loss Point:** LP-P3 (constraint dilution)
**Defects prevented:** P1 false positives, constraint violation defects

**Problem:** Domain constraints are formatted as a flat bulleted list:
```
## Domain Constraints
- Only import from: X, Y, Z
- Do not use relative imports
- Define utility functions before classes
- Prefer stdlib when sufficient
```

Binding constraints ("only import from") are mixed with advisory guidance ("prefer stdlib"), and the lead architect/drafter may treat all equally or ignore all equally.

**Requirements:**
- `_create_spec()` MUST use the `format_constraints()` function from the prompt loader to group constraints by category.
- The prime prompt loader MUST include a `format_constraints()` function with the same behavior as the artisan loader's `format_constraints()` (grouping by `[BINDING]`/`[STRUCTURAL]`/`[ADVISORY]` prefix tags).
- The spec prompt template MUST use the categorized format:
  ```
  ## Constraints
  ### Binding (must not violate)
  - Only import from: X, Y, Z
  - Do not use relative imports

  ### Structural (code organization)
  - Define utility functions before classes

  ### Advisory (prefer but not blocking)
  - Prefer stdlib when sufficient
  ```
- Alternatively, the prime loader MAY delegate to the artisan loader's `format_constraints()` to avoid code duplication. A shared utility would be acceptable.

### IMP-P6: Spec-to-Draft Validation

**Loss Point:** LP-P5 (no spec validation)
**Defects prevented:** All compression-loss defects (safety net)

**Problem:** If the lead architect's spec drops a critical parameter (e.g., the spec mentions `AlloyDBVectorStore.create_sync()` but omits `embedding_service`), the drafter faithfully implements the incomplete spec. There is no validation between spec creation and draft creation.

**Requirements:**
- After `_create_spec()` produces the spec and before `_create_draft()` is called, the system MUST check whether critical parameters from enrichment data are mentioned in the spec text.
- For any resolved parameter NOT found in the spec text, a warning MUST be appended to the drafter's feedback:
  ```
  ## Spec Completeness Warning
  The following parameters from requirements are NOT mentioned in the spec.
  Ensure these are included in your implementation:
  - user="postgres" (from requirements)
  - embedding_service=GoogleGenerativeAIEmbeddings (from requirements)
  ```
- This check MUST be text scanning only (no LLM call).
- When no parameters are missing, no warning MUST be injected.
- The validation logic SHOULD reuse the same pattern as the artisan's IMP-7 in `context_seed_handlers.py`.

---

## Part C: Shared Prompt Utilities

### REQ-PPE-005: Shared Constraint Formatter

Both the artisan and prime routes need the same `format_constraints()` behavior. Rather than duplicating:

- Extract `format_constraints()` to a shared module: `src/startd8/contractors/prompt_utils.py`
- Both `artisan_phases/prompts/__init__.py` and `workflows/builtin/prompts/__init__.py` MUST import from the shared module.
- The artisan loader's existing `format_constraints()` MUST remain importable from its current location (re-export for backward compatibility).

### REQ-PPE-006: Shared Parameter Validation

Both the artisan (IMP-7) and prime (IMP-P6) routes need the same "scan text for resolved parameters" logic:

- Extract the scanning function to `src/startd8/contractors/prompt_utils.py`:
  ```python
  def find_missing_parameters(
      text: str,
      resolved_parameters: list[dict],
  ) -> list[dict]:
      """Return resolved parameters whose key_value is not found in text."""
  ```
- Both artisan and prime validation gates MUST use this shared function.

---

## Files Modified

| File | Changes |
|------|---------|
| `src/startd8/workflows/builtin/prompts/__init__.py` | NEW — loader module |
| `src/startd8/workflows/builtin/prompts/lead_contractor.yaml` | NEW — 6 prompts |
| `src/startd8/workflows/builtin/prompts/prime_context.yaml` | NEW — 5 prompts |
| `src/startd8/workflows/builtin/lead_contractor_workflow.py` | YAML loading, structured context (IMP-P1), protocol guidance (IMP-P4), constraint categorization (IMP-P5), spec validation (IMP-P6) |
| `src/startd8/contractors/prime_contractor.py` | YAML loading for inline strings, requirements_text passthrough (IMP-P2), critical parameter extraction (IMP-P3) |
| `src/startd8/contractors/generators/lead_contractor.py` | YAML loading for retry/role hints |
| `src/startd8/contractors/prompt_utils.py` | NEW — shared format_constraints + find_missing_parameters |
| `src/startd8/contractors/artisan_phases/prompts/__init__.py` | Delegate format_constraints to shared module |
| `src/startd8/contractors/queue.py` | FeatureSpec.requirements_text field |
| `pyproject.toml` | Package data for YAML files |
| `tests/unit/workflows/test_prime_prompt_externalization.py` | NEW — tests |

---

## Implementation Order

```
Phase 1 (externalization only — no behavior change)
  REQ-PPE-001: YAML storage (create 2 YAML files with current prompt text)
  REQ-PPE-002: Loader module
  REQ-PPE-003: Package data
  REQ-PPE-004: Backward compatibility (replace inline constants with YAML-loaded values)
    │
Phase 2 (shared utilities)
  REQ-PPE-005: Extract format_constraints to shared module
  REQ-PPE-006: Extract parameter validation to shared module
    │
Phase 3 (quality improvements — prompt content changes)
  IMP-P1: Structured context in spec prompt
  IMP-P4: Protocol-aware spec guidance
  IMP-P5: Constraint categorization in spec
    │
Phase 4 (context flow changes — requires data model additions)
  IMP-P2: Requirements text passthrough
  IMP-P3: Critical parameter elevation
  IMP-P6: Spec-to-draft validation
```

---

## Test Strategy

Each change needs:
1. **Unit test** — verify the prompt contains expected content given mock inputs
2. **Negative test** — verify graceful degradation when optional fields are empty
3. **Regression** — existing LeadContractorWorkflow tests must pass

Test file: `tests/unit/workflows/test_prime_prompt_externalization.py`

### Test Cases

| # | Test | Validates |
|---|------|-----------|
| 1 | Load `lead_contractor.yaml` — all 6 prompts parseable | REQ-PPE-001 |
| 2 | Load `prime_context.yaml` — all 5 prompts parseable | REQ-PPE-001 |
| 3 | `get_template("lead_contractor", "spec")` returns string with `{task_description}` | REQ-PPE-002 |
| 4 | `format_prompt("lead_contractor", "spec", ...)` fills placeholders | REQ-PPE-002 |
| 5 | Missing YAML raises `FileNotFoundError` | REQ-PPE-002 |
| 6 | Missing prompt name raises `KeyError` | REQ-PPE-002 |
| 7 | `SPEC_PROMPT_TEMPLATE` module constant matches YAML-loaded value | REQ-PPE-004 |
| 8 | `_build_output_format()` returns correct format for single/multi file | REQ-PPE-004 |
| 9 | Spec prompt with structured context has dedicated sections | IMP-P1 |
| 10 | Spec prompt with empty architectural_context omits section | IMP-P1 |
| 11 | Spec prompt with requirements_text shows Requirements section | IMP-P2 |
| 12 | Spec prompt without requirements_text omits Requirements section | IMP-P2 |
| 13 | Critical parameters extracted from enrichment appear as dedicated section | IMP-P3 |
| 14 | No critical parameters → no Critical Parameters section | IMP-P3 |
| 15 | Spec prompt contains protocol guidance text | IMP-P4 |
| 16 | Constraints grouped by [BINDING]/[STRUCTURAL]/[ADVISORY] | IMP-P5 |
| 17 | Untagged constraints rendered as flat list | IMP-P5 |
| 18 | Missing parameters generate spec completeness warning | IMP-P6 |
| 19 | All parameters present → no warning | IMP-P6 |
| 20 | Shared format_constraints matches artisan behavior | REQ-PPE-005 |
| 21 | Shared find_missing_parameters detects absent keys | REQ-PPE-006 |

---

## Verification

After implementation:
- All new tests pass
- Existing `test_lead_contractor_workflow.py` tests pass unchanged
- Existing `test_prime_contractor.py` tests pass unchanged
- YAML files are included in `pip install -e .` (package data)
- `format_constraints()` is importable from both artisan and prime loader modules

---

## Relationship to Artisan Externalization

| Aspect | Artisan (REQ-PE-*) | Prime (REQ-PPE-*) |
|--------|--------------------|--------------------|
| YAML location | `contractors/artisan_phases/prompts/` | `workflows/builtin/prompts/` |
| Prompt count | 22 (4 YAML files) | 11 (2 YAML files) |
| Loader module | `artisan_phases/prompts/__init__.py` | `workflows/builtin/prompts/__init__.py` |
| Quality improvements | IMP-1 through IMP-7 | IMP-P1 through IMP-P6 |
| Shared utilities | `format_constraints()` | Same (via `prompt_utils.py`) |
| Status | Implemented | Specified |
