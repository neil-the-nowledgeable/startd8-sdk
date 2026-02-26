# Prime Contractor Prompt Size Analysis

**Date:** 2026-02-25  
**Context:** User observed ~84K input tokens for a single-feature run of `run-prime-contractor.sh` (online-boutique-demo, `--max-features 1`). This analysis identifies sources of prompt bloat and recommends mitigations.

---

## 1. Executive Summary

The Prime Contractor workflow (LeadContractorWorkflow) builds prompts from multiple context sources with **no aggregate token budget** and **minimal truncation**. For pipeline mode with rich seed context, a single feature can easily consume 80K+ input tokens across the spec → draft → review → integration phases.

**Primary contributors:**
1. **Plan context** — up to 60KB (~15K tokens) injected into every spec prompt
2. **Existing files** — up to 80KB (~20K tokens) in draft prompt for edit-mode tasks
3. **Architectural context** — full JSON passthrough, no truncation
4. **Redundant context** — structured keys extracted then re-serialized in `context_str`
5. **No per-section budgets** — plan, architecture, and remaining context are unbounded

---

## 2. Token Flow by Phase

### 2.1 SPEC Phase (Lead Agent)

**Location:** `lead_contractor_workflow.py` → `_build_spec_prompt()`

| Section | Source | Est. Size | Truncation |
|---------|--------|-----------|------------|
| `task_description` | `feature.description` | 0.5–2K tokens | None |
| `requirements_section` | `requirements_text` from metadata | 1–5K tokens | None |
| `critical_parameters_section` | `critical_parameters` from enrichment | 0.2–1K tokens | None |
| `context_sections` | Assembled from multiple keys | **15–40K tokens** | None |
| `domain_constraints` | DomainChecklist / output_constraint | 0.5–2K tokens | None |

**`context_sections` breakdown:**
- `## Context` — `json.dumps(context, indent=2)` of **remaining** keys after pops. Pipeline strategy adds `requirements_context`, `protocol_guidance`, `scope_boundary` (from `context_resolution.py`); these are **not** popped today, so they appear in the dump. **Duplication risk:** `requirements_text` is popped for a dedicated section, but `requirements_context` (formatted from same source) remains and duplicates content. PC-A3 deduplication audit should pop these when adding dedicated sections.
- `## Project Objectives` — `project_objectives` (from onboarding)
- `## Semantic Conventions` — `semantic_conventions` (from onboarding)
- `## Project Architecture` — `architectural_context` as full `json.dumps(arch_ctx, indent=2)` — **no truncation**
- `## Plan Context` — `plan_context` (full plan document text) — **capped at 60KB** in `load_seed_context()` only

**Plan context cap:** `prime_contractor.py` line 1100:
```python
self.plan_document_text = _text[:61440]  # 60KB cap
```
60KB ≈ 15K tokens. This is the **only** hard cap on plan context.

### 2.2 DRAFT Phase (Drafter Agent)

**Location:** `lead_contractor_workflow.py` → `_create_draft()` → `_build_existing_files_section()`

| Section | Source | Est. Size | Truncation |
|---------|--------|-----------|------------|
| `spec` | Lead's raw spec output | 2–8K tokens | None |
| `feedback` | Review feedback or initial message | 0.5–2K tokens | None |
| `output_format` | Per-file fencing instructions | 0.5–2K tokens | None |
| `existing_files_section` | **80KB budget** (`_EXISTING_FILES_BUDGET_BYTES`) | **~20K tokens** | Per-file truncation at budget boundary |

**Existing files budget:** `lead_contractor_workflow.py` line 91:
```python
_EXISTING_FILES_BUDGET_BYTES = 80 * 1024  # 80 KB
```
For edit-mode tasks, up to 80KB of existing file content is injected. Overflow files are omitted with a list; partial truncation within budget is applied per-file.

**Note:** Prime Contractor's `develop_feature()` does **not** populate `existing_files` in `gen_context`. That comes from the Artisan pipeline's `ImplementPhaseHandler`. For Prime-only runs (e.g. online-boutique greenfield), `existing_files` is typically empty unless a future enhancement adds edit-mode support.

### 2.3 REVIEW Phase (Lead Agent)

**Location:** `_review_draft()`

| Section | Source | Est. Size |
|---------|--------|-----------|
| `task_description` | Same as spec | 0.5–2K |
| `spec` | Full raw spec | 2–8K |
| `implementation` | Generated code | 2–15K (depends on output size) |
| `pass_threshold` | Numeric | negligible |

### 2.4 INTEGRATION Phase (Lead Agent)

**Location:** `_integrate_final()`

| Section | Source | Est. Size |
|---------|--------|-----------|
| `task_description` | Same as spec | 0.5–2K |
| `implementation` | Generated code | 2–15K |
| `review_history` | Truncated to 500 chars per review | ~1–2K |
| `integration_instructions` | From config | 0.2–1K |

---

## 3. Root Causes of 84K Tokens

### 3.1 Plan Context Dominance

- **60KB plan document** → ~15K tokens in **every** spec prompt
- Plan is loaded from `artifacts.plan_document_path` in the seed
- For online-boutique, the plan may be a full design/requirements doc
- **No task-scoped extraction** — the entire plan is injected regardless of task relevance

### 3.2 Architectural Context Unbounded

- `architectural_context` is passed as full JSON
- Plan ingestion derives this from the plan; it can include objectives, constraints, component_map, dependencies, shared_modules, etc.
- No character or token limit

### 3.3 Redundant Serialization

- `_build_spec_prompt()` pops `arch_ctx`, `plan_ctx`, `project_obj`, `sem_conv` for dedicated sections
- **But** `context_str = json.dumps(context, indent=2)` is built from the **remaining** context
- Pipeline strategy adds formatted sections (`requirements_context`, `protocol_guidance`, etc.) that may duplicate or overlap with raw JSON

### 3.4 Existing Files (Edit Mode)

- When Prime Contractor gains edit-mode support (or when used in a context that pre-populates `existing_files`), the 80KB budget applies
- 80KB ≈ 20K tokens in the draft prompt alone

### 3.5 Multiple LLM Calls per Feature

- 1 spec + 1–3 drafts + 1–3 reviews + 1 integration = 4–8 calls per feature
- Spec and draft phases carry the heaviest context
- **Cumulative:** 30K (spec) + 25K (draft) + 15K (review) + 10K (integration) ≈ 80K for a single feature

---

## 4. Recommendations

### 4.1 High Impact: Plan Context Truncation

**Current:** 60KB cap at load time; full text in every spec.

**Recommendation:** Add task-scoped truncation in `_build_spec_prompt()` or in `format_plan_context()`:

- **Option A:** Cap `plan_context` at 16KB (~4K tokens) in the spec prompt, with a trailing note: `"... [truncated; full plan in artifacts]"` — aligns with implementation plan PC-B1. For more aggressive reduction, 8K chars (~2K tokens) is an alternative.
- **Option B:** Extract only plan sections relevant to the task's `target_files` (e.g. grep for file names, include surrounding paragraphs)
- **Option C:** Add `plan_context_budget_chars` to HandlerConfig/artisan YAML (e.g. 16384) and truncate in `context_formatters.format_plan_context()`

**Implementation hint:** `context_formatters.py` → `format_plan_context()` — add optional `max_chars` parameter; call from `PipelineContextStrategy.resolve_task_context()` with budget.

### 4.2 High Impact: Architectural Context Budget

**Current:** Full JSON passthrough.

**Recommendation:**
- Add `architectural_context_budget_chars` (e.g. 4000)
- Truncate or summarize: keep `objectives` (first 3), `constraints` (first 5), `component_map` (top-level keys only), drop verbose nested content
- Or: format as compact bullets instead of `json.dumps(indent=2)`

### 4.3 Medium Impact: Existing Files Budget Reduction

**Current:** 80KB for edit-mode existing files.

**Recommendation:**
- Reduce `_EXISTING_FILES_BUDGET_BYTES` to 40KB (20K tokens) for draft prompt
- Or make it configurable via `HandlerConfig` / lead_contractor YAML
- Prioritize edit-target files; for create targets, omit or use minimal stub

### 4.4 Medium Impact: Deduplicate Context

**Current:** `context_str` includes keys that are also rendered as dedicated sections.

**Recommendation:**
- Audit `_build_spec_prompt()`: ensure all structured keys are popped before `json.dumps(context)`
- Avoid putting `plan_context`, `architectural_context`, `project_objectives`, `semantic_conventions` in the general context dict when they have dedicated sections

### 4.5 Low Impact: Add Per-Phase Token Budgets

**Recommendation:**
- Add `spec_context_budget_tokens` (e.g. 12000) to artisan/prime config
- Implement progressive truncation: plan_context → arch_context → requirements → project_objectives
- Log when truncation is applied for observability

---

## 5. Quick Wins (Minimal Code Changes)

| Change | File | Effect |
|--------|------|--------|
| Reduce plan cap from 60KB to 16KB | `prime_contractor.py:1100` | ~15K → ~4K tokens for plan |
| Reduce existing files budget from 80KB to 40KB | `lead_contractor_workflow.py:91` | ~20K → ~10K tokens for edit mode |
| Add plan truncation in spec prompt | `lead_contractor_workflow.py:_build_spec_prompt` | Cap `plan_ctx` at 16KB before appending (aligns with PC-B1) |

---

## 6. Observability

To validate future changes:

1. **Log prompt sizes** — Add debug logging of `len(prompt)` in `_create_spec`, `_create_draft`, `_review_draft`, `_integrate_final`
2. **OTel span attributes** — Emit `gen_ai.prompt.chars` or `gen_ai.prompt.tokens` (estimated) per phase
3. **Result JSON** — `total_input_tokens` is already in `prime-result-*.json`; add per-phase breakdown

---

## 7. Implementation Plan

A detailed implementation plan adopting seven Artisan IMPLEMENT patterns (mode-aware prompts, quantitative constraints, ordering, conditional framing, modular assembly, budget/truncation, YAML externalization) is specified in:

**[PRIME_PROMPT_ARTISAN_PATTERNS_IMPLEMENTATION.md](PRIME_PROMPT_ARTISAN_PATTERNS_IMPLEMENTATION.md)**

---

## 8. Code References (Verified)

| Location | Line(s) | Purpose |
|----------|---------|---------|
| `prime_contractor.py` | 1100 | Plan load cap: `_text[:61440]` (60KB) |
| `lead_contractor_workflow.py` | 91 | `_EXISTING_FILES_BUDGET_BYTES = 80 * 1024` |
| `lead_contractor_workflow.py` | 858–974 | `_build_spec_prompt()` — pops structured keys, builds context_sections |
| `lead_contractor_workflow.py` | 94–180 | `_build_existing_files_section()` — 80KB budget, per-file truncation |
| `context_resolution.py` | 802–929 | `PipelineContextStrategy.resolve_task_context()` — adds `requirements_context`, `protocol_guidance`, `scope_boundary` |

---

## 9. References

- `src/startd8/contractors/prime_contractor.py` — `load_seed_context()`, `develop_feature()`
- `src/startd8/contractors/context_resolution.py` — `PipelineContextStrategy.resolve_task_context()`
- `src/startd8/workflows/builtin/lead_contractor_workflow.py` — `_build_spec_prompt()`, `_create_draft()`, `_build_existing_files_section()`
- `src/startd8/contractors/context_formatters.py` — `format_plan_context()`, `format_architectural_context()`
- `docs/design/prime/PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md` — Context flow, requirements
