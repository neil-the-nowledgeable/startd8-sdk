# Prime Contractor: Artisan Pattern Adoption — Formal Implementation Plan

**Version:** 1.0.0  
**Created:** 2026-02-25  
**Status:** Draft  
**Implements:** [PRIME_PROMPT_ARTISAN_PATTERNS_IMPLEMENTATION.md](PRIME_PROMPT_ARTISAN_PATTERNS_IMPLEMENTATION.md)  
**Tracks:** [PRIME_PROMPT_ARTISAN_PATTERNS_CHECKLIST.md](PRIME_PROMPT_ARTISAN_PATTERNS_CHECKLIST.md)

---

## 1. Overview

### 1.1 Objective

Adopt seven proven patterns from the Artisan IMPLEMENT phase to improve Prime Contractor prompt quality, reduce token consumption (~84K → target ≤50K for single-feature runs), and align edit-mode behavior with the Mottainai Principle.

### 1.2 Scope

**In scope:**
- Budget and truncation (Pattern 6) — plan, arch, existing files, spec context caps
- Modular assembly (Pattern 5) — section builders, deduplication audit
- Conditional framing (Pattern 4) — edit vs create plan/arch framing
- Quantitative constraints (Pattern 2) — line-count directives in spec and draft
- Mode-aware system prompts (Pattern 1) — drafter edit/create/search_replace
- Ordering (Pattern 3) — `existing_files` population for Prime-only runs
- YAML externalization (Pattern 7) — complete coverage, no hardcoded prompts

**Out of scope:**
- Artisan pipeline changes beyond reference patterns
- Plan ingestion upstream changes
- ContextCore integration changes

### 1.3 Success Criteria

| ID | Criterion | Validation |
|----|-----------|------------|
| AC-1 | Single-feature run with pipeline mode consumes ≤50K input tokens (down from ~84K) | Integration test with online-boutique-demo |
| AC-2 | Edit-mode task receives edit_system prompt and existing-files-before-spec ordering | Unit test with mock `existing_files` |
| AC-3 | Plan context in spec prompt ≤16KB | Unit test with 60KB plan |
| AC-4 | Architectural context in spec prompt ≤4KB | Unit test with large `arch_ctx` |
| AC-5 | All prompt templates loadable from YAML; fallback works when YAML missing | Unit test with removed YAML |

---

## 2. Phase Summary

| Phase | Focus | Patterns | Est. Effort | Dependencies |
|-------|-------|----------|-------------|-------------|
| **P1** | Budget + Modular | 6, 5 | 2–3 days | None |
| **P2** | Framing + Quantitative | 4, 2 | 1–2 days | P1 |
| **P3** | Mode-aware + Ordering | 1, 3 | 2 days | P1, PC-O1 |
| **P4** | YAML Externalization | 7 | 1 day | P1–P3 |

---

## 3. Phase 1: Budget and Modular Assembly

**Goal:** Reduce token bloat via truncation and refactor spec prompt assembly for maintainability.

### 3.1 Tasks

| Task | ID | Requirement | File(s) | Description |
|------|-----|-------------|---------|-------------|
| **P1.1** | PC-B5 | Plan load cap | `prime_contractor.py` | Change `_text[:61440]` to `_text[:16384]` at line 1100. Add `_PLAN_LOAD_MAX_BYTES = 16_384` constant. |
| **P1.2** | PC-B1 | Plan truncation in spec | `lead_contractor_workflow.py` | Add `plan_context_max_chars` (default 16_384). Truncate `plan_ctx` with marker `"... [truncated; full plan in artifacts]"` before appending to sections. |
| **P1.3** | PC-B2 | Arch truncation | `lead_contractor_workflow.py` | Add `arch_context_max_chars` (default 4_096). Truncate or summarize `arch_ctx` when exceeding. Keep `objectives` (first 3), `constraints` (first 5). |
| **P1.4** | PC-B3 | Existing files budget | `lead_contractor_workflow.py` | Reduce `_EXISTING_FILES_BUDGET_BYTES` from 80KB to 40KB, or add `existing_files_budget_bytes` config. |
| **P1.5** | PC-B4 | Spec context budget | `lead_contractor_workflow.py` | Add `spec_context_budget_chars` (default 12_000). Progressive truncation: plan → arch → requirements → project_objectives. Log when truncation applied. |
| **P1.6** | PC-A1 | Section builders | `lead_contractor_workflow.py` | Extract `_build_spec_context_section()`, `_build_spec_plan_section()`, `_build_spec_arch_section()`, `_build_spec_objectives_section()`, `_build_spec_conventions_section()`. Each returns `str`. |
| **P1.7** | PC-A2 | Remove redundant dump | `lead_contractor_workflow.py` | Ensure all structured keys are popped before `json.dumps(context)`. `context_str` contains only keys not in dedicated sections. |
| **P1.8** | PC-A3 | Deduplication audit | `lead_contractor_workflow.py` | Pop `requirements_context`, `protocol_guidance`, `scope_boundary` (from `PipelineContextStrategy`). Add dedicated sections or render and pop to avoid duplication. |

### 3.2 Implementation Hints

- Add `_truncate_with_marker(text: str, max_chars: int, marker: str) -> str` helper.
- Reuse `context_formatters.format_plan_context()` with optional `max_chars` parameter if present.
- Emit OTel span event or log when truncation is applied.

### 3.3 Tests

| Test | Description |
|------|-------------|
| `test_plan_context_truncated_in_spec` | Pass 60KB plan; assert `plan_ctx` in spec prompt ≤16KB and trailing marker present. |
| `test_arch_context_truncated` | Pass large `arch_ctx`; assert `arch_context` section ≤4KB. |
| `test_spec_context_budget_enforced` | Pass context exceeding 12KB; assert progressive truncation order and log. |
| `test_plan_load_cap_reduced` | Load 60KB plan; assert `plan_document_text` length ≤16KB. |
| `test_section_builders_used` | Assert `_build_spec_prompt()` delegates to `_build_spec_*` helpers. |
| `test_no_duplication_in_context_str` | Assert `context_str` does not contain `plan_context`, `architectural_context`, `requirements_context`, `protocol_guidance`, `scope_boundary` when popped. |

### 3.4 Deliverables

- [x] `prime_contractor.py` — `_PLAN_LOAD_MAX_BYTES = 16_384`, plan cap at 1100
- [x] `lead_contractor_workflow.py` — truncation helpers, section builders, deduplication pops
- [x] `tests/unit/test_lead_contractor_workflow.py` — TestSpecPromptPhase1, TestPlanLoadCap, TestExistingFilesBudget

### 3.5 Exit Criteria

- All P1 tests pass.
- `pytest tests/unit/contractors/ tests/unit/workflows/ -v` — no regressions.
- Single-feature run with 60KB plan: spec prompt ≤ ~20K tokens (down from ~25K).

---

## 4. Phase 2: Conditional Framing and Quantitative Constraints

**Goal:** Frame plan and arch context differently for edit vs create; add numeric line constraints in spec and draft.

### 4.1 Tasks

| Task | ID | Requirement | File(s) | Description |
|------|-----|-------------|---------|-------------|
| **P2.1** | PC-F1 | Plan context framing | `lead_contractor_workflow.py` | When `existing_files` or `edit_mode.mode == "edit"`, prepend to plan: "The following plan excerpt describes CHANGES to apply to existing code. Do NOT treat it as a greenfield specification." Create mode: "The following plan excerpt provides context for this task. The design document (if present) is authoritative." |
| **P2.2** | PC-F2 | Arch context framing | `lead_contractor_workflow.py` | When edit mode, prefix arch: "Apply these architectural constraints to the existing file(s). Do not redesign from scratch." |
| **P2.3** | PC-F3 | Task verb | `lead_contractor_workflow.py` | Use "update" for edit, "implement" for create in task summary labels. |
| **P2.4** | PC-Q1 | Quantitative spec constraint | `lead_contractor_workflow.py` | In edit preamble, add: "The existing file(s) total X lines. Your spec must result in a draft that is AT LEAST Y lines (80% of X)." Compute X from `existing_files` line counts. |
| **P2.5** | PC-Q2 | Verify draft output format | `lead_contractor_workflow.py` | Confirm `_build_output_format()` passes `min_output_lines` and `existing_line_summary` for edit mode. |
| **P2.6** | PC-Q3 | Configurable threshold | `lead_contractor.yaml` or config | Add `edit_min_pct` (default 80).

### 4.2 Implementation Hints

- Framing text can be YAML templates or inline until P4.
- `edit_min_pct` lookup: `context.get("edit_min_pct", 80)` or config.

### 4.3 Tests

| Test | Description |
|------|-------------|
| `test_plan_context_edit_framing` | With `existing_files`, assert plan section has edit preamble. |
| `test_plan_context_create_framing` | Without `existing_files`, assert plan section has create preamble. |
| `test_arch_context_edit_framing` | With edit mode, assert arch section has edit prefix. |
| `test_quantitative_spec_constraint` | With `existing_files` totaling 100 lines, assert spec preamble includes "AT LEAST 80 lines". |

### 4.4 Deliverables

- [x] `lead_contractor_workflow.py` — framing logic in `_build_spec_plan_section()`, `_build_spec_arch_section()`, edit preamble
- [x] Unit tests for framing and quantitative constraints

### 4.5 Exit Criteria

- All P2 tests pass.
- Edit-mode spec with 100-line existing file shows "AT LEAST 80 lines" in preamble.

---

## 5. Phase 3: Mode-Aware Prompts and Ordering

**Goal:** Drafter receives mode-specific system prompt; Prime populates `existing_files` for edit tasks.

### 5.1 Tasks

| Task | ID | Requirement | File(s) | Description |
|------|-----|-------------|---------|-------------|
| **P3.1** | PC-O1 | Populate `existing_files` | `prime_contractor.py` or `context_resolution.py` | When `feature.target_files` contains paths that exist under `project_root`, read contents (subject to budget) and add `existing_files: {path: content}` to `gen_context`. Invoke in `develop_feature()` before calling `context_strategy.resolve_task_context()` or add to strategy result. |
| **P3.2** | PC-O2 | Verify ordering | `lead_contractor_workflow.py` | Confirm `DRAFT_EDIT_PROMPT_TEMPLATE` places `existing_files_section` before `spec`. No change if already correct. |
| **P3.3** | PC-O3 | Budget for existing files | `lead_contractor_workflow.py` | Use 40KB (from P1.4) or configurable. |
| **P3.4** | PC-M1 | Spec preamble | `lead_contractor_workflow.py` | Verify existing edit preamble in `_build_spec_prompt()` lines 884–895. No change if present. |
| **P3.5** | PC-M2 | Drafter system prompt | `lead_contractor_workflow.py` | Add `_get_drafter_system_prompt(context)`. When `existing_files` and any file ≥50 lines, return `search_replace_system`. When `existing_files`, return `edit_system`. Else `create_system`. |
| **P3.6** | PC-M3 | YAML templates | `lead_contractor.yaml` | Add `draft_system_edit`, `draft_system_create`, `draft_system_search_replace`. |
| **P3.7** | PC-M4 | Inline fallback | `lead_contractor_workflow.py` | Each `_format_*` for system prompts has fallback when YAML unavailable. |
| **P3.8** | Wire system prompt | `lead_contractor_workflow.py` | Call `drafter_agent.generate(prompt, system_prompt=sys_prompt)` in `_create_draft()`. |

### 5.2 Implementation Hints

- `_SEARCH_REPLACE_LINE_THRESHOLD`: Use 50 (Artisan default) or configurable. Reference `development.py:2312`.
- `existing_files` population: read files in `develop_feature()` before passing to `code_generator.generate()`. Apply budget per `_build_existing_files_section()` logic.
- Agent API: `generate(prompt, system_prompt=...)` passes `**kwargs` to `agenerate()`.

### 5.3 Tests

| Test | Description |
|------|-------------|
| `test_existing_files_populated_for_edit` | Feature with `target_files` pointing to existing files; assert `gen_context["existing_files"]` populated. |
| `test_drafter_edit_system_prompt` | With `existing_files`, assert drafter receives `edit_system` (or equivalent). |
| `test_drafter_search_replace_system_prompt` | With `existing_files` and file ≥50 lines, assert `search_replace_system`. |
| `test_drafter_create_system_prompt` | Without `existing_files`, assert `create_system`. |
| `test_draft_edit_ordering` | With `existing_files`, assert `existing_files_section` appears before `spec` in prompt. |

### 5.4 Deliverables

- [x] `prime_contractor.py` — `existing_files` population in `develop_feature()`
- [x] `lead_contractor_workflow.py` — `_get_drafter_system_prompt()`, `drafter.generate(..., system_prompt=...)`
- [x] `lead_contractor.yaml` — `draft_system_edit`, `draft_system_create`, `draft_system_search_replace`
- [x] Unit tests for mode selection and ordering

### 5.5 Exit Criteria

- All P3 tests pass.
- Edit-mode task (existing files on disk) receives edit_system and correct ordering.
- AC-2 satisfied.

---

## 6. Phase 4: YAML Externalization

**Goal:** All prompt fragments in YAML; no hardcoded strings; graceful fallback.

### 6.1 Tasks

| Task | ID | Requirement | File(s) | Description |
|------|-----|-------------|---------|-------------|
| **P4.1** | PC-Y1 | Complete YAML coverage | `lead_contractor_workflow.py` | Audit for remaining inline strings. Move any to `lead_contractor.yaml`. |
| **P4.2** | PC-Y2 | Format helper | `lead_contractor_workflow.py` | Implement `_format_lead_prompt(template_name, **kwargs) -> Optional[str]`. When None (YAML missing), use module-level fallback. |
| **P4.3** | PC-Y3 | New templates | `lead_contractor.yaml` | Add `spec_edit_preamble`, `plan_context_edit_framing`, `plan_context_create_framing`, `arch_context_edit_framing` (from P2). Ensure `draft_system_*` from P3. |
| **P4.4** | PC-Y4 | Placeholders | `lead_contractor.yaml` | Document `placeholders` for each template. |

### 6.2 Implementation Hints

- Follow `lead_contractor_workflow.py` → `_get_prime_template()` pattern.
- Fallback: `try: return _get_template(...); except (FileNotFoundError, KeyError): return None`

### 6.3 Tests

| Test | Description |
|------|-------------|
| `test_yaml_fallback_when_missing` | Temporarily remove or rename YAML; assert workflow still runs with fallback strings. |
| `test_all_templates_loadable` | Assert each template loads without error. |

### 6.4 Deliverables

- [x] `lead_contractor_workflow.py` — `_format_lead_prompt()`, no hardcoded prompts
- [x] `lead_contractor.yaml` — complete template set with placeholders
- [x] Unit test for YAML fallback

### 6.5 Exit Criteria

- All P4 tests pass.
- AC-5 satisfied: YAML fallback works when file missing.

---

## 7. Milestones and Timeline

| Milestone | Phase | Target | Validation |
|-----------|-------|--------|-------------|
| **M1** | P1 complete | Token reduction | Spec prompt ≤20K tokens; plan load ≤16KB |
| **M2** | P2 complete | Framing | Edit vs create framing in spec |
| **M3** | P3 complete | Edit mode | `existing_files` populated; drafter system prompt |
| **M4** | P4 complete | Externalization | All prompts in YAML |
| **M5** | All | AC-1 | Single-feature run ≤50K input tokens |

**Estimated total effort:** 6–8 days.

---

## 8. Risk Register

| ID | Risk | Mitigation |
|----|------|------------|
| R1 | Truncation breaks task relevance | Plan truncation keeps first 16KB; add task-scoped extraction if needed (future) |
| R2 | `existing_files` population adds I/O latency | Budget caps; read only when target files exist |
| R3 | System prompt not supported by all agents | Fallback: omit system_prompt when agent doesn't support it; user prompt still works |
| R4 | YAML path differs in downstream installs | Fallback constants ensure graceful degradation |

---

## 9. References

- [PRIME_PROMPT_ARTISAN_PATTERNS_IMPLEMENTATION.md](PRIME_PROMPT_ARTISAN_PATTERNS_IMPLEMENTATION.md) — Requirements and design
- [PRIME_PROMPT_ARTISAN_PATTERNS_CHECKLIST.md](PRIME_PROMPT_ARTISAN_PATTERNS_CHECKLIST.md) — Tracking checklist
- [PRIME_PROMPT_SIZE_ANALYSIS.md](PRIME_PROMPT_SIZE_ANALYSIS.md) — Token flow, root causes
- [PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md](PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md) — YAML structure
- [PROJECT_CENTRIC_ARTISAN_REQUIREMENTS.md](../artisan/PROJECT_CENTRIC_ARTISAN_REQUIREMENTS.md) — PCA layers
