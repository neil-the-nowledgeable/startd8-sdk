# startd8-sdk Improvement Suggestions

Suggestions to improve output quality for the PlanIngestionWorkflow and Artisan workflow. startd8-sdk provides the workflow implementations consumed by Wayfinder.

## Artisan Context Seed Structure

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | **Standard `onboarding` top-level key** | Define a canonical `onboarding` block with `artifact_manifest_path`, `project_context_path`, `artifact_type_schema`, `output_path_conventions`, `semantic_conventions`, `export_provenance_checksum`. |
| 2 | **Task → artifact type mapping** | Add `artifact_types_addressed: ["dashboard", "prometheus_rule"]` (or similar) to each task config so generators know which types the task handles. |
| 3 | **Design doc template hints** | Add `design_doc_sections` per task (e.g., "Parameter validation", "Error handling") to guide design doc generation. |
| 4 | **Token budget per task** | Add `estimated_tokens` or `max_output_tokens` per task so the workflow can cap output size. |

## PlanIngestionWorkflow

| # | Suggestion | Rationale |
|---|------------|-----------|
| 5 | **Merge onboarding metadata into seed** | When context files include `onboarding-metadata.json`, merge its contents into the produced context seed under `artifacts` / `onboarding`. |
| 6 | **Seed schema validation** | Validate the produced seed against a JSON schema before writing. |
| 7 | **Artifact manifest path in artifacts** | Ensure `artifacts.artifact_manifest_path` and `artifacts.project_context_path` are set when onboarding metadata is available. |

## Artisan Workflow (Design / Implement)

| # | Suggestion | Rationale |
|---|------------|-----------|
| 8 | **Pass artifact manifest path** | Provide the artifact manifest path in the handoff so implementers can load it directly. |
| 9 | **Include example artifact in context** | For each artifact type, include a small example (e.g., ServiceMonitor YAML) in the seed or handoff. |
| 10 | **Constraint pre-flight** | Before generation, re-check constraints against the current codebase and fail fast if blocking constraints are violated. |
| 11 | **Coverage-aware handoff** | Include `coverage_gaps` in the handoff so implementers know which artifacts to generate first. |
| 12 | **Test-first for implement tasks** | For implement tasks, require that tests are written/updated before generation. |

## Design Handoff

| # | Suggestion | Rationale |
|---|------------|-----------|
| 13 | **design-handoff.json schema** | Document and validate the handoff structure for implement phase. |
| 14 | **Context file list in handoff** | Include the list of context files (with checksums) the design was based on. |

## Cross-Project Consistency

| # | Suggestion | Rationale |
|---|------------|-----------|
| 15 | **Shared schema version** | Use a single version for artifact manifest, onboarding metadata, and seed so consumers can branch on version. |
| 16 | **Provenance chain** | Propagate `source_checksum` from export → onboarding → ingestion → seed. |

---

## Priority Order

| Priority | Items | Effort |
|----------|-------|--------|
| High | 1, 5, 7, 8 | 2–3 days |
| Medium | 2, 6, 10, 11, 13 | 1–2 days |
| Low | 3, 4, 9, 12, 14, 15, 16 | 1–2 days |

## Implementation Notes

- **Item 1**: Update `PlanIngestionWorkflow` output schema to include optional `onboarding` block.
- **Item 5**: Add logic in `PlanIngestionWorkflow` to detect `onboarding-metadata.json` among context files and merge into seed.
- **Item 8**: Add `artifact_manifest_path` and `project_context_path` to the design handoff JSON produced by `run_artisan_design_only.py`.
- **Item 10**: Add a pre-generation step that loads constraints from the seed and checks the codebase.

## Related Repos

- **ContextCore** — [docs/IMPROVEMENT_SUGGESTIONS_2026-02-12.md](../ContextCore/docs/IMPROVEMENT_SUGGESTIONS_2026-02-12.md) (export command, onboarding metadata)
- **Wayfinder** — [docs/IMPROVEMENT_SUGGESTIONS_2026-02-12.md](../wayfinder/docs/IMPROVEMENT_SUGGESTIONS_2026-02-12.md) (plan ingestion scripts)

---

## Validation Review (2026-02-12)

Validated against the startd8-sdk codebase. Each suggestion is marked as **correct/needs clarification** and notes any overlaps with existing behavior.

### Artisan Context Seed Structure

| # | Status | Notes |
|---|--------|-------|
| **1** | ✅ Correct | `ArtisanContextSeed` (`plan_ingestion_models.py`) has `artifacts: Dict[str, str]` with only `plan_document_path` and `review_config_path`. No `onboarding` block exists. |
| **2** | ✅ Correct | Task config in `_derive_tasks_from_features` has `config.context` with `feature_id`, `target_files`, `estimated_loc` only. No `artifact_types_addressed`. |
| **3** | ⚠️ Partial | `design_calibration` already exists per task with `sections`, `depth_tier`, `max_output_tokens`. Suggestion adds `design_doc_sections` per task — `sections` might overlap; clarify if distinct from calibration. |
| **4** | ⚠️ Partial | `design_calibration` already includes `max_output_tokens` per task (for design doc generation). Implementation phase uses `truncation_detection` and `estimated_lines` but no per-task `max_output_tokens`. Suggestion adds it for implement phase. |

### PlanIngestionWorkflow

| # | Status | Notes |
|---|--------|-------|
| **5** | ✅ Correct | `PlanIngestionWorkflow` does not read `onboarding-metadata.json`. `context_files` come from config; no merge logic exists. Wayfinder must pass `onboarding-metadata.json` as a context file; SDK would need merge logic. |
| **6** | ✅ Correct | `atomic_write_json` in `_phase_emit` writes the seed without schema validation. `WorkflowBase` has optional jsonschema for *input* config, not output. |
| **7** | ✅ Correct | `artifacts` dict currently only has `plan_document_path` and `review_config_path`. No `artifact_manifest_path` or `project_context_path`. Manifest context comes from `.contextcore.yaml` via `_extract_manifest_context` but is not stored in `artifacts`. |

### Artisan Workflow (Design / Implement)

| # | Status | Notes |
|---|--------|-------|
| **8** | ✅ Correct | `HandoffData` (`handoff.py`) has `enriched_seed_path`, `project_root`, `output_dir`, `workflow_id`, `design_results`, `scaffold`. No `artifact_manifest_path` or `project_context_path`. Implement phase reads seed via `enriched_seed_path`; adding paths to handoff is valid. |
| **9** | ✅ Correct | No example artifacts in seed or handoff. Would improve context for artifact-type generators. |
| **10** | ⚠️ Needs clarification | PLAN phase logs a warning when `preflight_failures > 0` but does **not** abort (`context_seed_handlers.py:501`). Domain preflight runs pre-generation and produces `CheckStatus.FAIL`, but `preflight_failures` in plan output is informational. Suggestion: add explicit abort when blocking constraints fail. Clarify: "blocking constraints" = architectural `constraints` from manifest with `severity: blocking`, or preflight `FAIL` checks? |
| **11** | ✅ Correct | Handoff has no `coverage_gaps`. Implement phase would need coverage analysis before generation. |
| **12** | ⚠️ Needs clarification | Current flow: IMPLEMENT → TEST → REVIEW → FINALIZE. Test-first would invert to TEST before IMPLEMENT. Significant architectural change; clarify scope (e.g., only for specific task types or artifact generators). See [IMPROVEMENT_SUGGESTIONS_CLARIFICATIONS.md](IMPROVEMENT_SUGGESTIONS_CLARIFICATIONS.md) for details. |

### Design Handoff

| # | Status | Notes |
|---|--------|-------|
| **13** | ✅ Correct | `HandoffData` has dataclass structure and `load_design_handoff` validates schema version and required keys. No JSON schema file or formal documentation. |
| **14** | ✅ Correct | Handoff has no `context_files` or checksums. Design phase uses `architectural_context` from seed; context file list is not persisted. |

### Cross-Project Consistency

| # | Status | Notes |
|---|--------|-------|
| **15** | ✅ Correct | Seed has `version: "1.0.0"`; handoff has `schema_version: 1`. No shared version across artifact manifest, onboarding metadata, and seed. |
| **16** | ✅ Correct | No `source_checksum` propagation in PlanIngestionWorkflow or seed. |

### Corrections to Implementation Notes

- **Item 8**: Handoff is written by `write_design_handoff` in `handoff.py`, called from both `run_artisan_design_only.py` and `run_artisan_workflow.py` (when `--stop-after design`). Update the note to mention both callers.
- **Item 10**: Add that PLAN phase currently only warns on preflight failures; implement would need to either (a) add `--abort-on-preflight-fail` to PLAN, or (b) add a pre-IMPLEMENT phase that re-runs preflight and aborts on FAIL.

### Summary

| Category | Valid | Partial / Clarify | Total |
|----------|-------|-------------------|-------|
| Seed structure | 2 | 2 | 4 |
| PlanIngestion | 3 | 0 | 3 |
| Artisan workflow | 2 | 2 | 4 |
| Handoff | 2 | 0 | 2 |
| Cross-project | 2 | 0 | 2 |
| **Total** | **11** | **4** | **15** |

All suggestions are technically feasible; four need clarification or overlap with existing behavior. **See [IMPROVEMENT_SUGGESTIONS_CLARIFICATIONS.md](IMPROVEMENT_SUGGESTIONS_CLARIFICATIONS.md) for detailed clarification questions.** Priority order is reasonable for implementation sequencing.
