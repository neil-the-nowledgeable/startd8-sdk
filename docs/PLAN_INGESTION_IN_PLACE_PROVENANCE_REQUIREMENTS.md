# Plan Ingestion In-Place Output + Run Provenance Requirements

**Version:** 1.0.0  
**Created:** 2026-02-14  
**Scope:** `startd8 workflow run plan-ingestion`

---

## Goal

Default `plan-ingestion` to update stable, existing output document paths in place, and emit a run-level provenance artifact that proves exactly which input files were used and which outputs were written for each run.

This feature prevents output sprawl, improves freshness confidence, and strengthens downstream auditability.

---

## Problem Statement

Current pipeline usage can produce multiple generated plan variants over time. This makes it harder to:

1. Keep a single canonical generated document current.
2. Verify whether latest source edits were reflected in the newest output.
3. Reconstruct a run lineage from inputs to outputs quickly.

---

## Functional Requirements

### PI-IP-001: Write strategy input

- The workflow MUST accept `document_write_strategy`.
- Allowed values MUST be:
  - `update_existing` (default)
  - `new_output`
- Invalid values MUST fail validation with a clear error.

### PI-IP-002: Explicit target path input

- The workflow MUST accept optional `ingested_document_path`.
- When provided, this path MUST be used as the transform output target.
- Relative paths MUST resolve against `output_dir`.

### PI-IP-003: Deterministic target resolution order

When `document_write_strategy=update_existing`, target resolution MUST be:

1. explicit `ingested_document_path` (if provided),
2. prior run `plan_document_path` from `.startd8/plan_ingestion_state.json` (if exists and route-compatible),
3. fallback default path:
   - artisan: `output_dir/PLAN-ingested.md`
   - prime: `output_dir/plan-ingestion-tasks.yaml`

### PI-IP-004: Route compatibility guard

- Prior state path reuse MUST be gated by route compatibility:
  - artisan route -> markdown extension (`.md`/`.markdown`)
  - prime route -> yaml extension (`.yaml`/`.yml`)
- If incompatible, workflow MUST ignore prior path and use fallback resolution.

### PI-IP-005: Safe in-place write semantics

- Output writes MUST remain atomic.
- In-place updates MUST retain backup behavior (`backup=True`) to reduce destructive risk.

### PI-IP-006: Fallback transform parity

- If transform LLM step fails and deterministic fallback is enabled, fallback output MUST be written to the same resolved target path (not a separate variant path).

### PI-IP-007: Provenance artifact emission

- The workflow MUST emit `run-provenance.json` to `output_dir`.
- Emission MUST occur for successful runs.

### PI-IP-008: Provenance minimum schema

`run-provenance.json` MUST include:

1. run metadata: `run_id`, `started_at`, `completed_at`, `workflow_id`, `workflow_version`,
2. selected route and plan title,
3. write strategy and output path resolution details,
4. selected config snapshot fields relevant to reproducibility,
5. input file references with:
   - `path`
   - `exists`
   - `mtime` (UTC ISO timestamp when available)
   - `sha256` (when file exists),
6. output file references with the same fingerprint fields,
7. quality summary (`requirements_coverage_percent`, `artifact_mapping_percent`, `conflict_count`),
8. references to key artifacts when present:
   - `preflight-report.json`
   - `ingestion-traceability.json`
   - `review-config.json`
   - `artisan-context-seed.json` (or equivalent route artifact)

### PI-IP-009: Workflow result contract

- Workflow output MUST include `run_provenance_path`.
- Existing output keys MUST remain intact to preserve compatibility.

### PI-IP-010: State continuity

- Workflow MUST continue persisting `.startd8/plan_ingestion_state.json`.
- Successful runs MUST update `plan_document_path` to the resolved target path used for writes.

---

## Validation and Error Handling Requirements

### PI-IP-011: Validation behavior

- Invalid `document_write_strategy` MUST fail early before execution.

### PI-IP-012: Missing prior state path behavior

- Missing or unreadable prior state path MUST NOT fail the run.
- Workflow MUST degrade gracefully to fallback target resolution.

### PI-IP-013: Missing file fingerprint behavior

- Provenance generation MUST tolerate missing files.
- Missing files MUST be represented with `exists=false` and null fingerprint fields.

---

## Non-Functional Requirements

### PI-IP-014: Backward compatibility

- Default behavior change to `update_existing` MUST not break existing callers that rely on current output keys.

### PI-IP-015: Low operational overhead

- Provenance generation SHOULD use local file metadata and hashing only.
- No network dependency is allowed for provenance emission.

### PI-IP-016: Auditability

- A single run artifact MUST be sufficient to reconstruct:
  - inputs consumed,
  - outputs produced,
  - route chosen,
  - quality snapshot at completion.

---

## Test Requirements

### PI-IP-T001

- Validate invalid `document_write_strategy` rejects config.

### PI-IP-T002

- Validate prior-state in-place path is reused when present and route-compatible.

### PI-IP-T003

- Validate explicit `ingested_document_path` overrides prior state and fallback.

### PI-IP-T004

- Validate fallback default path is used when no valid prior path exists.

### PI-IP-T005

- Validate `run-provenance.json` is emitted and includes expected input/output checksums.

---

## Downstream Success Criteria

1. Repeated `plan-ingestion` runs update the same canonical output path by default.
2. Teams can verify source-to-output lineage from `run-provenance.json` alone.
3. Gate 2 -> Gate 3 handoff can assert artifact freshness using provenance evidence.
