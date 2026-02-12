# Improvement Suggestions — Clarifications Needed

Items from [IMPROVEMENT_SUGGESTIONS_2026-02-12.md](IMPROVEMENT_SUGGESTIONS_2026-02-12.md) that need clarification or overlap with existing behavior.

---

## Item 3: Design doc template hints

**Suggestion:** Add `design_doc_sections` per task (e.g., "Parameter validation", "Error handling") to guide design doc generation.

**Overlap:** `design_calibration` already exists per task with `sections`, `depth_tier`, `max_output_tokens`, and `depth_guidance` (see `PlanIngestionWorkflow._derive_design_calibration`). The calibration's `sections` come from `DEPTH_TIERS` (brief/standard/comprehensive).

**Clarification needed:**
- Is `design_doc_sections` per task meant to override or supplement the calibration `sections`?
- Is `design_doc_sections` task-specific content (e.g., "Parameter validation", "Error handling") while `sections` are structural (e.g., "Overview", "Architecture", "Data Model")?

---

## Item 4: Token budget per task

**Suggestion:** Add `estimated_tokens` or `max_output_tokens` per task so the workflow can cap output size.

**Overlap:** `design_calibration` already includes `max_output_tokens` per task for design doc generation. The implementation phase uses `truncation_detection` and `estimated_lines` but does not have per-task `max_output_tokens`.

**Clarification needed:**
- Is this for the **implement** phase only (design phase already has it)?
- Is it for both design and implement, with design being the existing calibration?

---

## Item 10: Constraint pre-flight

**Suggestion:** Before generation, re-check constraints against the current codebase and fail fast if blocking constraints are violated.

**Current behavior:** PLAN phase logs a warning when `preflight_failures > 0` but does **not** abort (`context_seed_handlers.py:501`). Domain preflight runs pre-generation and produces `CheckStatus.FAIL`, but `preflight_failures` in plan output is informational only.

**Clarification needed:**
- Does "blocking constraints" mean:
  - (a) Architectural `constraints` from manifest with `severity: blocking`, or
  - (b) Preflight check results with `CheckStatus.FAIL`?
- Is the desired behavior: add `--abort-on-preflight-fail` to PLAN, or add a pre-IMPLEMENT phase that re-runs preflight and aborts on FAIL?

---

## Item 12: Test-first for implement tasks

**Suggestion:** For implement tasks, require that tests are written/updated before generation.

**Current behavior:** Flow is IMPLEMENT → TEST → REVIEW → FINALIZE. Test-first would invert to TEST before IMPLEMENT.

**Clarification needed:**
- Does this apply to all implement tasks or only specific task types (e.g., artifact generators)?
- Is this TDD-style (write tests first, then implement to pass) or a weaker form (e.g., ensure test scaffolding exists before generation)?

---

## Answers

### Item 3: Design doc template hints

- **Override vs supplement:** `design_doc_sections` should **supplement** the calibration. The calibration `sections` define the structural outline (Overview, Architecture, Data Model, etc.). `design_doc_sections` adds task-specific content hints that guide *what to emphasize within* those sections for a given task.
- **Distinction:** Yes. `sections` are structural (e.g., "Overview", "Architecture", "Data Model", "Error Handling", "Testing Strategy"). `design_doc_sections` are task-specific content hints (e.g., "Parameter validation for Jinja2 variables", "Error handling for missing artifact spec"). For a ServiceMonitor generator task, the Data Model section might get an extra hint: "Document the mapping from artifact spec parameters to ServiceMonitor YAML fields."

### Item 4: Token budget per task

- **Scope:** Primarily for the **implement** phase. The design phase already has `max_output_tokens` via `design_calibration`. The implement phase generates code (and can produce large outputs); per-task `max_output_tokens` there would help prevent runaway generation and truncation.
- **Recommendation:** Add `max_output_tokens` per task for the implement phase, mirroring the design calibration pattern. Keep design as-is; implement gains the same capability.

### Item 10: Constraint pre-flight

- **"Blocking constraints" meaning:** Both (a) and (b) are related. Manifest constraints with `severity: blocking` are the source; when violated, they should produce preflight `CheckStatus.FAIL`. So (a) is the source of truth, (b) is the runtime result. "Blocking constraints" = manifest constraints with `severity: blocking` that have been checked and resulted in `CheckStatus.FAIL`.
- **Desired behavior:** Both options are useful:
  1. **`--abort-on-preflight-fail` for PLAN** — For immediate feedback when starting the workflow. If preflight fails, don't proceed to design.
  2. **Pre-IMPLEMENT phase** — Re-run preflight before code generation. The codebase may have changed between design and implement; a fresh check before writing code avoids violating constraints introduced during design.

### Item 12: Test-first for implement tasks

- **Scope:** Apply to **artifact generator tasks** (and similar template-and-test pairs), not all implement tasks. For tasks that follow the pattern "implement X, then add tests for X" (e.g., PI-006 ServiceMonitor generator + PI-007 ServiceMonitor tests), the scaffolding-first approach applies.
- **Style:** A **weaker form** — ensure test scaffolding exists (test file, test class skeleton, fixture for the artifact type) before generating the implementation. Full TDD (write passing assertions first, then implement) would be heavy for every task. Scaffolding-first is a reasonable middle ground: the test file and structure exist, so the implementer knows the contract before generating code.

---

## Summary

| Item | Main issue |
|------|------------|
| 3 | Overlap with `design_calibration.sections`; clarify override vs supplement |
| 4 | Overlap with `design_calibration.max_output_tokens`; clarify implement-phase scope |
| 10 | PLAN does not abort on preflight failures; clarify "blocking" definition |
| 12 | Inverts phase order; clarify scope and TDD vs scaffolding |
