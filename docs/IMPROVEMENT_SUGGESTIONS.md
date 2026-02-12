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

- **ContextCore** — [docs/IMPROVEMENT_SUGGESTIONS.md](../ContextCore/docs/IMPROVEMENT_SUGGESTIONS.md) (export command, onboarding metadata)
- **Wayfinder** — [docs/IMPROVEMENT_SUGGESTIONS.md](../wayfinder/docs/IMPROVEMENT_SUGGESTIONS.md) (plan ingestion scripts)
