# Prime Contractor: Artisan Pattern Adoption — Implementation Plan

**Status:** Draft  
**Date:** 2026-02-25  
**Parent:** [PRIME_PROMPT_SIZE_ANALYSIS.md](PRIME_PROMPT_SIZE_ANALYSIS.md), [PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md](PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md)  
**Formal Plan:** [PRIME_PROMPT_ARTISAN_PATTERNS_PLAN.md](PRIME_PROMPT_ARTISAN_PATTERNS_PLAN.md)  
**Source:** Design insights from Artisan IMPLEMENT phase rewrite (commits 8cccbc1, 2b4f3dc, 1e97e4a, dfbf022)

---

## 1. Objective

Adopt seven proven patterns from the Artisan IMPLEMENT phase rewrite to improve Prime Contractor prompt quality, reduce token consumption (~84K → target ~40K for single-feature runs), and align edit-mode behavior with the Mottainai Principle.

| # | Pattern | Artisan Reference | Prime Target |
|---|---------|------------------|--------------|
| 1 | Mode-aware system prompts | `implement.yaml` create_system, edit_system, search_replace_system | Lead contractor spec + draft |
| 2 | Quantitative constraints | `edit_first_directive` min_lines, `_MIN_OUTPUT_FRACTION` | Spec + draft output format |
| 3 | Ordering (existing before spec) | `DRAFT_EDIT_PROMPT_TEMPLATE` | `_create_draft()` when existing_files present |
| 4 | Conditional framing | `design_doc_edit` vs `design_doc_create` | Spec context sections |
| 5 | Modular assembly | `_build_*` helpers in development.py | `_build_spec_prompt()` refactor |
| 6 | Budget and truncation | `_MAX_EXISTING_TOTAL`, `_MAX_EXISTING_FILE_BYTES` | Per-section budgets |
| 7 | YAML externalization | `implement.yaml` + `_format_implement_prompt()` | `lead_contractor.yaml` (already partial) |

---

## 2. Pattern 1: Mode-Aware System Prompts

### 2.1 Current State

LeadContractorWorkflow uses a single spec prompt and a single draft prompt. There is no system-prompt differentiation for edit vs create tasks. The drafter receives the same framing regardless of whether target files exist.

### 2.2 Artisan Pattern

`development.py` → `_get_system_prompt(chunk)` returns:
- `search_replace_system` when `_use_search_replace` (large existing files)
- `edit_system` when `_existing_file_contents` or `edit_mode.mode == "edit"`
- `create_system` otherwise

### 2.3 Requirements

| ID | Requirement | Location | Acceptance |
|----|-------------|----------|------------|
| PC-M1 | **Spec preamble for edit mode.** When `context.get("existing_files")` or `context.get("edit_mode", {}).get("mode") == "edit"`, prepend an "EDIT MODE — Existing Code Modification" preamble to the spec prompt (already implemented in `_build_spec_prompt` lines 884–895). | `lead_contractor_workflow.py` | Spec LLM sees edit framing when modifying existing files |
| PC-M2 | **Drafter system prompt selection.** Add `_get_drafter_system_prompt(context)` to LeadContractorWorkflow. When `existing_files` present and any file ≥ `_SEARCH_REPLACE_LINE_THRESHOLD` (Artisan uses 50 lines — `development.py:_SEARCH_REPLACE_LINE_THRESHOLD`; Prime may use 50 or a higher value like 200–400 for its use case), return `search_replace_system`. When `existing_files` present, return `edit_system`. Otherwise return `create_system`. | `lead_contractor_workflow.py` | Drafter receives mode-appropriate system prompt |
| PC-M3 | **YAML templates for mode-specific system prompts.** Add `spec_edit_preamble`, `draft_system_edit`, `draft_system_create`, `draft_system_search_replace` to `lead_contractor.yaml`. | `prompts/lead_contractor.yaml` | Templates editable without code change |
| PC-M4 | **Inline fallback.** Each `_format_*` call must have a fallback when YAML is unavailable (e.g. downstream installs). | `lead_contractor_workflow.py` | Graceful degradation when prompts missing |

### 2.4 Implementation Hints

- Reuse `DRAFT_EDIT_PROMPT_TEMPLATE` structure (existing files before spec) — already in place.
- Agent API supports `system_prompt` via kwargs: `base.py` `generate()` forwards `**kwargs` to `agenerate()`; Claude, Gemini, OpenAI agents accept `system_prompt: Optional[str]`. Call `drafter_agent.generate(prompt, system_prompt=sys_prompt)` when mode-specific system prompt is available.
- Lead contractor agents (Claude) typically accept `system` vs `user` message split; drafter agents (Gemini Flash, GPT-4.1-nano) may vary.

---

## 3. Pattern 2: Quantitative Constraints

### 3.1 Current State

- `_EDIT_MIN_PCT = 80` and `_DRAFT_SIZE_REGRESSION_THRESHOLD = 0.50` exist but are used for post-generation validation.
- Spec and draft prompts use soft language ("must strive to preserve", "do not rewrite").
- No explicit line-count in the spec prompt.

### 3.2 Artisan Pattern

- `edit_first_directive` includes: "Your output MUST be AT LEAST {min_lines} lines (80% of original). Outputs significantly shorter will be REJECTED."
- `single_file_edit_output` and `multi_file_edit_output` include per-file line constraints.

### 3.3 Requirements

| ID | Requirement | Location | Acceptance |
|----|-------------|----------|------------|
| PC-Q1 | **Quantitative spec constraint for edit.** When building edit-mode spec preamble, include: "The existing file(s) total X lines. Your spec must result in a draft that is AT LEAST Y lines (80% of X)." | `_build_spec_prompt()` | Spec LLM sees numeric constraint |
| PC-Q2 | **Quantitative draft output format.** `single_file_edit_output` and `multi_file_edit_output` already include `min_output_lines` and `existing_line_summary`. Ensure these are passed through to `_build_output_format()` (already implemented). | `lead_contractor_workflow.py` | Draft output format shows explicit line counts |
| PC-Q3 | **Configurable threshold.** Add `edit_min_pct` to `HandlerConfig` or `lead_contractor` config (default 80). | `lead_contractor.yaml` or config | Threshold adjustable without code change |

### 3.4 Implementation Hints

- `_build_output_format()` already computes `min_output_lines` for edit mode.
- Add `edit_min_pct` to `lead_contractor.yaml` config section if present.
- Log when threshold is applied for observability.

---

## 4. Pattern 3: Ordering (Existing Before Spec)

### 4.1 Current State

`DRAFT_EDIT_PROMPT_TEMPLATE` (PCA-605) already places existing files before the spec. The template structure is:

```
existing_files_section
spec
feedback
output_format
```

So ordering is **already implemented** for the draft phase when `existing_files` is present.

### 4.2 Gap

Prime Contractor's `develop_feature()` does **not** populate `existing_files` in `gen_context`. The `context_strategy.resolve_task_context()` does not add `existing_files`. Only the Artisan pipeline does this via `ImplementPhaseHandler`.

### 4.3 Requirements

| ID | Requirement | Location | Acceptance |
|----|-------------|----------|------------|
| PC-O1 | **Populate existing_files for edit tasks.** When `feature.target_files` contains paths that exist on disk under `project_root`, read their contents (subject to budget) and add `existing_files: {path: content}` to `gen_context`. | `prime_contractor.py` → `develop_feature()` or `context_strategy` | Edit mode gets existing file content |
| PC-O2 | **Ordering preserved.** When `existing_files` is present, `_create_draft()` uses `DRAFT_EDIT_PROMPT_TEMPLATE` which places `existing_files_section` before `spec`. No change needed if PC-O1 is done. | `lead_contractor_workflow.py` | Existing code appears before spec in draft prompt |
| PC-O3 | **Budget for existing files.** Use same `_EXISTING_FILES_BUDGET_BYTES` (80KB) or a configurable value. Consider reducing to 40KB per PRIME_PROMPT_SIZE_ANALYSIS. | `lead_contractor_workflow.py` | Budget prevents token overflow |

---

## 5. Pattern 4: Conditional Framing (Edit vs Create)

### 5.1 Current State

- Spec prompt: `context_sections` includes `## Plan Context` and `## Project Architecture` with no distinction for edit vs create.
- Plan context is always framed as "full plan" — no "changes to apply" framing for edit mode.

### 5.2 Artisan Pattern

- `design_doc_edit`: "The following design document describes CHANGES to apply to the existing code…”
- `design_doc_create`: "This design document OVERRIDES the Task Summary below when they differ…”

### 5.3 Requirements

| ID | Requirement | Location | Acceptance |
|----|-------------|----------|------------|
| PC-F1 | **Plan context framing.** When `existing_files` is present or `edit_mode.mode == "edit"`, prepend to plan context: "The following plan excerpt describes CHANGES to apply to existing code. Do NOT treat it as a greenfield specification." When create mode, use: "The following plan excerpt provides context for this task. The design document (if present) is authoritative." | `_build_spec_prompt()` or `context_formatters.format_plan_context()` | Plan context framed differently for edit vs create |
| PC-F2 | **Architectural context framing.** When edit mode, prefix arch context: "Apply these architectural constraints to the existing file(s). Do not redesign from scratch." | `_build_spec_prompt()` | Arch context doesn't bias toward rewrite |
| PC-F3 | **Task description verb.** Use "update" for edit, "implement" for create in any task summary labels (already partially done in B-1/B-7 for Artisan).

---

## 6. Pattern 5: Modular Assembly

### 6.1 Current State

`_build_spec_prompt()` is a single method that:
1. Pops structured keys from context
2. Builds `context_sections` via `json.dumps(context)` plus ad-hoc sections
3. Assembles everything into one template

The "context" section is a monolithic JSON dump plus appended sections.

### 6.2 Artisan Pattern

`_build_task_description()` delegates to helpers:
- `_build_project_identity`
- `_build_target_files`
- `_build_existing_files`
- `_build_edit_first_directive`
- `_build_edit_mode_classification`
- `_build_design_framing`
- `_build_supplementary_context`
- `_build_retry_feedback`

### 6.3 Requirements

| ID | Requirement | Location | Acceptance |
|----|-------------|----------|------------|
| PC-A1 | **Extract section builders.** Refactor `_build_spec_prompt()` into helpers: `_build_spec_context_section()`, `_build_spec_plan_section()`, `_build_spec_arch_section()`, `_build_spec_objectives_section()`, `_build_spec_conventions_section()`. Each returns a string or empty. | `lead_contractor_workflow.py` | Spec prompt built from composable parts |
| PC-A2 | **Remove redundant context dump.** Ensure all structured keys are popped before `json.dumps(context)`. The `context_str` should contain only keys that have no dedicated section. | `_build_spec_prompt()` | No duplication of plan/arch/objectives in context_str |
| PC-A3 | **Deduplication audit.** Document which keys are popped vs remain. Current pops: `existing_files`, `edit_mode`, `domain_constraints`, `requirements_text`, `critical_parameters`, `arch_ctx`, `plan_ctx`, `project_obj`, `sem_conv`. **Pipeline strategy adds** (from `PipelineContextStrategy.resolve_task_context()`): `requirements_context`, `protocol_guidance`, `scope_boundary` — these are **not** popped today and end up in `context_str`, duplicating content. Add pops for these when adding dedicated sections, or render them in dedicated sections and pop to avoid duplication. | `_build_spec_prompt()` | No key appears in both dedicated section and context_str |

---

## 7. Pattern 6: Budget and Truncation

### 7.1 Current State

- Plan: 60KB cap at load time (`prime_contractor.py:1100`).
- Existing files: 80KB cap in draft (`_EXISTING_FILES_BUDGET_BYTES`).
- Architectural context: no cap.
- No per-section truncation in spec prompt.

### 7.2 Artisan Pattern

- `_MAX_EXISTING_TOTAL = 120_000` for Artisan (development.py).
- `_MAX_EXISTING_FILE_BYTES` per-file truncation.
- Progressive truncation with "[TRUNCATED: N lines omitted]" markers.

### 7.3 Requirements

| ID | Requirement | Location | Acceptance |
|----|-------------|----------|------------|
| PC-B1 | **Plan context truncation in spec.** Add `plan_context_max_chars` (default 16_384 = 16KB) to spec prompt assembly. Truncate `plan_ctx` with trailing marker: "... [truncated; full plan in artifacts]". | `_build_spec_prompt()` | Plan in spec ≤ 16KB (~4K tokens) |
| PC-B2 | **Architectural context truncation.** Add `arch_context_max_chars` (default 4_096). When `arch_ctx` exceeds, truncate or summarize: keep `objectives` (first 3), `constraints` (first 5), drop verbose nested content. | `_build_spec_prompt()` | Arch context ≤ 4KB (~1K tokens) |
| PC-B3 | **Existing files budget reduction.** Reduce `_EXISTING_FILES_BUDGET_BYTES` from 80KB to 40KB, or make configurable. | `lead_contractor_workflow.py` | Edit mode draft ≤ 40KB existing files |
| PC-B4 | **Spec context budget.** Add `spec_context_budget_chars` (default 12_000). Under budget pressure, truncate in order: plan_context → arch_context → requirements → project_objectives. Log truncation. | `_build_spec_prompt()` | Aggregate spec context bounded |
| PC-B5 | **Plan load cap reduction.** Reduce `load_seed_context()` plan cap from 60KB to 16KB. | `prime_contractor.py` | Plan loaded ≤ 16KB |

### 7.4 Implementation Hints

- Reuse `context_formatters.format_plan_context()` with optional `max_chars` parameter.
- Add `_truncate_with_marker(text: str, max_chars: int, marker: str) -> str` helper.
- Emit OTel span event or log when truncation is applied for observability.

---

## 8. Pattern 7: YAML Externalization

### 8.1 Current State

Lead contractor prompts are partially externalized in `lead_contractor.yaml` (spec, draft, review, integration, etc.). `prime_context.yaml` exists for output_constraint, prior_error_feedback, etc. Some prompts remain inline or hardcoded.

### 8.2 Artisan Pattern

- All prompts in `implement.yaml` with `_format_implement_prompt(template_name, **kwargs)`.
- Inline fallback when YAML is unavailable (FileNotFoundError, KeyError) → return None, caller uses hardcoded string.

### 8.3 Requirements

| ID | Requirement | Location | Acceptance |
|----|-------------|----------|------------|
| PC-Y1 | **Complete YAML coverage.** All prompt fragments used in LeadContractorWorkflow MUST be in `lead_contractor.yaml`. Audit for any remaining inline strings. | `lead_contractor_workflow.py` | No hardcoded prompt strings |
| PC-Y2 | **Format helper with fallback.** Use `_format_lead_prompt(template_name, **kwargs) -> Optional[str]` pattern. When None, use module-level fallback constant. | `lead_contractor_workflow.py` | Graceful degradation |
| PC-Y3 | **New templates for mode-specific prompts.** Add `spec_edit_preamble`, `draft_system_edit`, `draft_system_create`, `draft_system_search_replace`, `plan_context_edit_framing`, `plan_context_create_framing` to YAML. | `prompts/lead_contractor.yaml` | Mode-specific text editable |
| PC-Y4 | **Documentation.** Placeholders in YAML must be documented. `placeholders` field is advisory. | `lead_contractor.yaml` | Each template has placeholders list |

---

## 9. Implementation Order

| Phase | Patterns | Dependencies | Est. Effort |
|-------|----------|--------------|-------------|
| **P1** | 6 (Budget), 5 (Modular) | None | 2–3 days |
| **P2** | 4 (Conditional framing), 2 (Quantitative) | P1 | 1–2 days |
| **P3** | 1 (Mode-aware), 3 (Ordering) | PC-O1 (existing_files population) | 2 days |
| **P4** | 7 (YAML completeness) | P1–P3 | 1 day |

**Recommended sequence:** P1 first (budget + modular) reduces token bloat immediately. P2 improves framing. P3 requires Prime to support edit mode (existing_files). P4 is cleanup.

---

## 10. Acceptance Criteria Summary

| ID | Criterion | Validation |
|----|-----------|------------|
| AC-1 | Single-feature run with pipeline mode consumes ≤ 50K input tokens (down from ~84K). | Integration test with online-boutique-demo |
| AC-2 | Edit-mode task (existing files) receives edit_system prompt and existing-files-before-spec ordering. | Unit test with mock existing_files |
| AC-3 | Plan context in spec prompt ≤ 16KB. | Unit test with 60KB plan |
| AC-4 | Architectural context in spec prompt ≤ 4KB. | Unit test with large arch_ctx |
| AC-5 | All prompt templates loadable from YAML; fallback works when YAML missing. | Unit test with removed YAML |

---

## 11. Cross-References

- [PRIME_PROMPT_SIZE_ANALYSIS.md](PRIME_PROMPT_SIZE_ANALYSIS.md) — Token flow, root causes, quick wins
- [PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md](PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md) — YAML structure, loader API
- [PROJECT_CENTRIC_ARTISAN_REQUIREMENTS.md](../artisan/PROJECT_CENTRIC_ARTISAN_REQUIREMENTS.md) — PCA layers, edit-first behavior
- `src/startd8/contractors/artisan_phases/prompts/implement.yaml` — Artisan reference templates
- `src/startd8/contractors/artisan_phases/development.py` — Artisan `_build_*` helpers, `_SEARCH_REPLACE_LINE_THRESHOLD` (line 2312), `_MAX_EXISTING_TOTAL` (line 1658), `_MAX_EXISTING_FILE_BYTES` (line 936)

---

## 12. Context Flow (Verified)

- `gen_context` is built by `context_strategy.resolve_task_context(feature_data, seed_data, ...)` in `prime_contractor.py` → `develop_feature()`.
- `gen_context` is passed to `code_generator.generate(context=gen_context)` → `LeadContractorWorkflow.run(config)`.
- `_build_spec_prompt()` receives a **copy** of `gen_context` (caller passes `dict(context)` to avoid mutation).
- `existing_files` is **not** populated by `resolve_task_context()` — only Artisan's `ImplementPhaseHandler` does. PC-O1 adds this for Prime-only runs.
