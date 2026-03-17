# OpenSpec Adapter — Requirements

**Author:** agent:claude-code
**Date:** 2026-03-17
**Status:** Draft
**Scope:** Lightweight adapter that reads OpenSpec artifact directories and feeds them into the existing plan ingestion pipeline

---

## Context

[OpenSpec](https://github.com/Fission-AI/OpenSpec) is a lightweight spec-driven development framework that organizes work into structured markdown artifacts:

```
openspec/changes/{change-name}/
├── proposal.md          # Why + scope
├── specs/               # Requirements (Given/When/Then scenarios)
│   ├── {domain}/spec.md
│   └── ...
├── design.md            # Technical approach
└── tasks.md             # Implementation checklist
```

StartD8's plan ingestion pipeline already accepts a plan document + optional requirements files. The adapter maps OpenSpec's artifact structure to these existing inputs — no architectural changes to the pipeline itself.

### Non-Goals

- No dependency on OpenSpec's npm package or Node.js runtime
- No modification to the plan ingestion pipeline phases (PARSE, ASSESS, TRANSFORM, REFINE, EMIT)
- No support for OpenSpec's slash command system (that's a separate tool-layer concern)
- Not a replacement for writing plan documents — an alternative input format

---

## Requirements

### REQ-OSA-001: Change Directory Discovery

The adapter MUST discover OpenSpec change directories by scanning for the conventional `openspec/changes/` path relative to a project root.

**Acceptance criteria:**
- Given a project root, scan `{project_root}/openspec/changes/` for subdirectories
- Each subdirectory containing a `proposal.md` is a valid change
- If no `openspec/changes/` directory exists, return empty (not an error)
- Support an explicit `--openspec-change` CLI arg that points directly to a single change directory, bypassing discovery

### REQ-OSA-002: Artifact Reading

The adapter MUST read the four standard OpenSpec artifact types and handle missing optional artifacts gracefully.

**Artifact mapping:**

| OpenSpec Artifact | Required? | Maps To |
|---|---|---|
| `proposal.md` | YES | Plan document preamble (goals, scope, rationale) |
| `specs/*.md` | NO | Requirements files (`requirements_files` config) |
| `design.md` | NO | Architectural context section in assembled plan |
| `tasks.md` | NO | Implementation checklist section in assembled plan |

**Acceptance criteria:**
- `proposal.md` MUST exist — adapter returns an error if missing
- `specs/` is recursively scanned: `specs/{domain}/spec.md` and `specs/*.md` patterns
- `design.md` and `tasks.md` are optional — their absence reduces context but doesn't block ingestion
- All files read as UTF-8 with `errors="replace"` for binary safety

### REQ-OSA-003: Plan Document Assembly

The adapter MUST assemble a single plan document from the OpenSpec artifacts in a format the PARSE phase can extract features from.

**Assembly order:**
1. **Proposal** — inserted as `## Proposal` section (goals, scope, approach)
2. **Design** — inserted as `## Technical Design` section (if present)
3. **Tasks** — inserted as `## Implementation Tasks` section (if present)

**Acceptance criteria:**
- Output is a single markdown string suitable for `plan_text` input
- Section headers are clear so PARSE can distinguish scope from implementation
- The assembled plan preserves the original markdown formatting within each artifact
- A `## Source` metadata line indicates the plan was assembled from OpenSpec (traceability)

### REQ-OSA-004: Requirements File Forwarding

The adapter MUST forward spec files as `requirements_files` to the plan ingestion config.

**Acceptance criteria:**
- Each `specs/{domain}/spec.md` file path is added to `requirements_files`
- Given/When/Then scenarios in specs are preserved verbatim (the PARSE LLM can extract acceptance criteria from them)
- If no specs exist, `requirements_files` is empty (not an error)

### REQ-OSA-005: Pipeline Integration

The adapter MUST integrate with the existing cap-dev-pipe pipeline runner as an alternative to `--plan`.

**Acceptance criteria:**
- New CLI option: `--openspec-change <path>` on `run-cap-delivery.sh` or `run-plan-ingestion.sh`
- Mutually exclusive with `--plan` (cannot specify both)
- When `--openspec-change` is used, the adapter assembles the plan and requirements, then feeds them to the same plan ingestion workflow
- The assembled plan path is written to a temporary file and passed as `plan_path` in the config
- Requirements files are passed as `requirements_files` in the config

### REQ-OSA-006: Delta Spec Handling

The adapter SHOULD support OpenSpec's delta spec format (ADDED/MODIFIED/REMOVED sections) when the change targets an existing codebase.

**Acceptance criteria:**
- Delta spec sections (ADDED, MODIFIED, REMOVED) are preserved in the forwarded requirements
- The PARSE prompt already handles negative_scope — REMOVED items naturally map to negative_scope extraction
- No special parsing needed — the LLM handles the structure in the requirements text

### REQ-OSA-007: Multi-Change Batching

The adapter MAY support ingesting multiple OpenSpec changes as a batch (analogous to a multi-feature plan).

**Acceptance criteria:**
- When `--openspec-change` points to `openspec/changes/` (the parent directory), all child changes are assembled into a single plan with one feature section per change
- Dependencies between changes (if declared in `.openspec.yaml`) are mapped to feature `dependencies` in the assembled plan
- Single-change mode (pointing to a specific change directory) is the default and simpler path

### REQ-OSA-008: Validation

The adapter MUST validate the OpenSpec directory structure before assembly.

**Acceptance criteria:**
- Error if `proposal.md` is missing
- Warning if `specs/` is empty (plan will have no requirements context)
- Warning if `tasks.md` is missing (PARSE can still extract features from proposal + design)
- Error if the change directory doesn't exist
- All validation errors reported before any LLM calls (fail-fast)

---

## Implementation Notes

### Placement

`src/startd8/seeds/openspec_adapter.py` — a single module with:
- `discover_openspec_changes(project_root: Path) -> List[Path]`
- `assemble_plan_from_openspec(change_dir: Path) -> Tuple[str, List[str]]` returning `(plan_text, requirements_file_paths)`
- `validate_openspec_change(change_dir: Path) -> List[str]` returning error messages

### Size Estimate

~150 lines of Python. No new dependencies. Reads markdown files, concatenates with section headers, returns strings.

### Testing

- Unit tests with a fixture directory containing sample OpenSpec artifacts
- Test assembly output format matches what PARSE can handle
- Test missing/optional artifact handling
- Test multi-spec discovery (`specs/auth/spec.md`, `specs/payments/spec.md`)

---

## Open Questions

1. **Should the adapter auto-discover changes or require explicit selection?** Multi-change batching (REQ-OSA-007) adds complexity. Starting with explicit `--openspec-change <path>` is simpler.

2. **Should `.openspec.yaml` metadata be parsed?** OpenSpec uses this for change-level config (status, dependencies). Parsing it would enable dependency ordering in multi-change mode but adds a YAML dependency on OpenSpec's schema.

3. **Should the assembled plan include the original OpenSpec directory structure as context for the LLM?** e.g., "This plan was assembled from OpenSpec artifacts in `openspec/changes/add-dark-mode/`" — useful for traceability but adds noise.
