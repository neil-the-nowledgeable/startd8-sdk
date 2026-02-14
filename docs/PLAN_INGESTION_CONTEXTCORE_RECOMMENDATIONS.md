# Plan Ingestion and ContextCore Recommendations

## Purpose

Capture design recommendations to improve plan-ingestion output quality for both Prime and Artisan workflows while keeping ContextCore decoupled as a specification/contract producer rather than an implementation orchestrator.

## Current State Summary

- `plan-ingestion` is primarily `plan_path` text driven, with optional enrichment from context files.
- The workflow already supports:
  - complexity-based routing (`prime` vs `artisan`)
  - optional forced route override
  - optional task tracking artifact generation
  - propagation of onboarding `source_checksum` into artisan seed
- `architectural_review_log` supports requirements-aware dual-document review, but plan-ingestion refine currently does not fully leverage that path as a first-class input.

## Three Inputs to Leverage Together

Treat these as one ingestion corpus:

1. ContextCore export artifacts (especially onboarding metadata + artifact manifest)
2. Design requirements document(s)
3. Implementation plan document

### Why

- ContextCore export defines contract intent ("what must exist").
- Requirements define acceptance and quality constraints ("what must be true").
- Plan defines execution proposal ("how to build it").

Higher quality comes from reconciling all three, not treating any single input as authoritative for every concern.

## Startd8 Plan-Ingestion Recommendations

## 1) Add First-Class Inputs

Add explicit config fields for:

- `contextcore_export_dir` (or explicit file paths for export outputs)
- `requirements_path` or `requirements_files`
- retain `plan_path` for implementation plan

Avoid overloading `context_files` for required upstream contract artifacts.

## 2) Add Gate 1: Export Contract Preflight (before PARSE)

Validate at ingestion boundary:

- expected export files present
- checksum integrity (`source_checksum`, `artifact_manifest_checksum`, `project_context_checksum`)
- parameter source resolvability summary exists and is acceptable
- coverage minimum or explicit gap list availability

On hard integrity failures, fail fast with specific error messages.

## 3) Build a Normalized Ingestion Corpus

Before parse/assess:

- normalize artifact contract info
- normalize requirements IDs/criteria/NFRs
- normalize plan features/dependencies

Generate reconciliation outputs:

- unmapped requirements
- unmapped artifacts/gaps
- conflicts between constraints and plan proposals

## 4) Strengthen Routing Decision

Route using both:

- complexity score (current)
- translation quality signals (new), such as:
  - requirements coverage %
  - artifact mapping completeness %
  - contract conflict count

Safeguard: if translation quality is low, bias toward artisan or fail with actionable diagnostics.

## 5) Upgrade REFINE to Requirements-Aware Mode

Pass requirements into architectural review dual-document mode:

- evaluate traceability from plan to requirements
- emit coverage gap suggestions explicitly
- keep plan and requirements suggestions separable for triage

## 6) Emit Traceability Artifact

Add `ingestion-traceability.json` with:

- requirement -> feature/task mappings
- artifact -> feature/task mappings
- unresolved and conflict entries with severity
- checksum/freshness evidence used during ingestion

This enables deterministic validation and downstream auditing.

## 7) Improve Output Contracts for Both Routes

For Prime task YAML and Artisan seed task entries, include:

- requirement IDs
- acceptance/test obligations
- source references (`contextcore`, `requirements`, `plan`)
- mapping rationale where conflicts were resolved

## ContextCore Recommendations (Decoupled, Spec-Oriented)

These changes are warranted and can remain non-coupled to startd8 internals.

## 1) Versioned Export Contract Schemas

Publish machine-readable schema definitions for:

- artifact manifest
- onboarding metadata
- provenance

Require `schema_version` with compatibility rules (major/minor semantics).

## 2) Stable Identity and Provenance Fields

Strengthen and document:

- stable `artifact_id` requirements
- canonical checksum algorithms and field semantics
- provenance chain invariants

Keep this generic, not workflow-specific.

## 3) Validation Report Output

Emit an export-time `validation-report.json` containing:

- completeness and coverage diagnostics
- resolvability diagnostics
- warnings/errors with severity and code

Downstream systems can gate on this report without embedding ContextCore rules.

## 4) Parameter Source Resolvability Metadata

Include machine-readable status for parameter source mappings:

- resolved/unresolved
- source path
- reason if unresolved

This improves deterministic gating and avoids late-stage failures.

## 5) Optional Requirements Bridge (Generic)

Add optional requirements hints in export metadata:

- requirement identifiers
- labels/priority
- acceptance anchors

Do not encode startd8 workflow phases or Prime/Artisan-specific fields.

## 6) Export Capability Flags

Include metadata such as:

- available optional sections (`artifact_task_mapping`, `coverage_gaps`, etc.)
- schema feature flags for downstream compatibility handling

## Non-Goals (to Prevent Tight Coupling)

ContextCore should not:

- encode startd8 routing thresholds
- emit Prime/Artisan task YAML/seed structures
- embed workflow phase semantics

Keep ContextCore as contract producer ("what"), and startd8 as translation/execution layer ("how").

## Phased Implementation Plan (Startd8)

1. Input and preflight phase
   - add explicit inputs
   - add Gate 1 integrity checks
   - add structured preflight errors

2. Corpus and reconciliation phase
   - normalize three-source corpus
   - emit traceability draft output
   - add mapping completeness metrics

3. Routing and refine phase
   - augment route decision with translation quality signals
   - wire requirements-aware dual-document refine
   - finalize output schema additions for prime/artisan

## Success Criteria

- no stale export ingestion when checksum chain breaks
- explicit visibility into missing requirement/artifact mappings before implementation
- improved first-pass output quality for both prime and artisan routes
- preserved architectural decoupling between ContextCore and startd8 internals
