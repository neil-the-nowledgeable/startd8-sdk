# Artisan Workflow Issues Catalog

**Purpose**: Comprehensive catalog of issues encountered while testing the Artisan Contractor workflow, organized into (A) issues observed first-hand in this development session and (B) issues documented from other sources.

**Date**: 2026-02-12  
**Project under test**: wayfinder (ContextCore observability stack)  
**Task**: PI-001 (Generator module skeleton — core infrastructure, Jinja registry, orchestration)

---

## Part A: Issues Observed in This Session

These issues were encountered during live runs of the Artisan workflow against the wayfinder project's PI-001 task.

---

### A-1: Multi-File Split Failure — LLM Consolidates All Code Into One File

**Phase**: IMPLEMENT  
**Severity**: High  
**Status**: Mitigated (defense-in-depth layers added)

**Symptom**: The drafter was asked to produce two files (`__init__.py` and `artifact_generators.py`). It put ~525 lines of real code into `__init__.py` and produced nothing for `artifact_generators.py`. The auto-stub mechanism wrote a placeholder stub for the missing file.

**Root cause**: LLMs commonly treat multi-file tasks as "just put it all in one file." When the prompt says "produce code for these 2 files," the model gravitates toward the larger/more interesting file and neglects `__init__.py` or secondary modules.

**Impact**: The auto-stub (`# STARTD8_AUTO_STUB`) satisfies the build requirement but the file has no real logic. Downstream tasks that import from the stubbed file will fail.

**Mitigation applied**:
- Gate 2c (Design-to-Implement Reconciliation): uses `_file_scope` metadata to identify downstream files and pre-stub them before the drafter runs
- Smart Retry Gate: skips expensive LLM retries when all missing files are downstream/shared
- Downstream File Stub Constraint: injects explicit prompt constraints telling the LLM to produce minimal stubs for non-primary files
- Review Guard: excludes expected downstream stubs from the review prompt to avoid false negatives

---

### A-2: Review Score Failed (62/80) but Workflow Reported Success

**Phase**: REVIEW  
**Severity**: Medium  
**Status**: Open (behavioral, not a bug)

**Symptom**: The REVIEW phase scored the PI-001 output at 62/80, which is below the passing threshold. However, the overall workflow status was reported as `completed` / `success`.

**Root cause**: The REVIEW phase failure does not block FINALIZE. The workflow treats the review as advisory — it logs the failure but continues to final assembly.

**Impact**: Users may see `status: success` and assume the code is production-ready when the review found significant quality issues.

**Potential fix**: Add a `--fail-on-review-failure` flag or make the review threshold configurable so users can choose to block finalization on review failure.

---

### A-3: `artifact_generators.py` Was an Auto-Stub, Not LLM-Generated

**Phase**: IMPLEMENT  
**Severity**: High  
**Status**: Mitigated (same as A-1)

**Symptom**: After IMPLEMENT, `artifact_generators.py` contained only:
```python
# STARTD8_AUTO_STUB
"""artifact_generators.py — auto-generated stub.

This file was not produced by the LLM drafter and has been
auto-stubbed to satisfy the multi-file build requirement.
Downstream tasks will implement the real logic.
"""
```

**Root cause**: The drafter consolidated all logic into `__init__.py`. The auto-stub mechanism filled in the missing file to prevent build failures, but this masks the actual generation failure.

---

### A-4: LOC Estimation Mismatch — Design Doc Implied ~500 LOC, Seed Estimated 80

**Phase**: DESIGN → IMPLEMENT  
**Severity**: Medium  
**Status**: Fixed (LOC mismatch detection added)

**Symptom**: The design document for PI-001 contained code snippets totaling ~500+ lines. The seed's `estimated_loc` was 80. This caused the depth tier to be "standard" (4096 tokens) instead of "comprehensive" (8192 tokens).

**Root cause**: Plan ingestion derives `estimated_loc` from the feature description heuristically. For infrastructure tasks with broad scope, this underestimates significantly.

**Impact**: The design phase was token-capped at 4096, causing truncation. The implement phase produced oversized code relative to the estimate, which triggers validation warnings.

**Fix applied**: Added LOC mismatch detection in `_tasks_to_chunks` that warns when the design doc's implied LOC exceeds `3x` the seed estimate. This surfaces the mismatch early so the user can adjust the seed or CLI flags.

---

### A-5: Generation Results Cache Prevents Fresh IMPLEMENT Runs

**Phase**: IMPLEMENT  
**Severity**: High  
**Status**: Documented (operational, not a bug)

**Symptom**: Across multiple re-runs (including with `--adopt-prior`), the IMPLEMENT phase completed in ~0.2s with `$0.00` cost. It was loading the cached failed result from `generation_results.json` instead of making a fresh LLM call.

**Root cause**: The `generation_results.json` file in `.startd8/state/` persists across runs. When `--adopt-prior` is used, it deliberately loads prior results. But if the prior result was a failure, the failure is re-loaded.

**Impact**: Users expect `--adopt-prior` to skip only successful prior results, not re-adopt failures.

**Workaround**:
- Delete `.startd8/state/generation_results.json` before re-running
- Use `ARTISAN_FORCE_IMPLEMENT=1` to force fresh generation
- The initial confusion was compounded by the state directory path changing from `.startd8_state/` to `.startd8/state/`

---

### A-6: Commit Failed for PI-001 (Silent Failure)

**Phase**: IMPLEMENT (post-generation)  
**Severity**: Medium  
**Status**: Open

**Symptom**: The workflow log showed `Commit failed for PI-001:` with no error message after the colon. This occurred on every run.

**Root cause**: The auto-commit step runs after successful generation. When the generated files are auto-stubs or were written to incorrect paths, the commit has nothing meaningful to commit, or git rejects the operation.

**Impact**: No files are committed to the wayfinder repo. The user must manually inspect and commit.

---

### A-7: Files Written to Project Root Instead of Target Directory

**Phase**: IMPLEMENT  
**Severity**: High  
**Status**: Resolved (cache cleared and re-run)

**Symptom**: Generated files (`__init__.py`, `artifact_generators.py`) appeared at the wayfinder project root rather than in `src/contextcore/generators/`.

**Root cause**: The LLM drafter's output was parsed, but the file-path extraction placed files relative to the project root instead of the target directory specified in the seed. The cached result in `generation_results.json` preserved these wrong paths.

**Impact**: Even after successful generation, the files are in the wrong location. Downstream imports fail, review fails.

**Resolution**: Cleared the cache and re-ran with corrected path handling.

---

### A-8: Design Phase Token Truncation

**Phase**: DESIGN  
**Severity**: Medium  
**Status**: Documented (operational)

**Symptom**:
```
WARNING [startd8.agents.claude] Response from claude-4 was truncated (stop_reason=max_tokens).
Output tokens: 4096. Consider increasing max_tokens (currently 4096).
```

**Root cause**: PI-001 used `depth_tier: "standard"` with `max_output_tokens: 4096`. The design doc for a broad infrastructure task (core generators, Jinja registry, orchestration) exceeds 4096 tokens.

**Impact**: Design document is truncated, missing later sections. Downstream phases work from an incomplete spec.

**Workarounds**:
- `--design-max-tokens 8192` CLI override
- Edit seed: `design_calibration.PI-001.max_output_tokens → 8192`
- Re-run plan ingestion with `comprehensive` depth tier for infrastructure tasks

---

### A-9: Design Section Mismatch Warnings (Parser vs. Calibration)

**Phase**: DESIGN  
**Severity**: Low  
**Status**: Fixed

**Symptom**:
```
WARNING [design_documentation] Design document missing section 'API Contracts' in iteration 1
WARNING [design_documentation] Design document missing section 'Security Considerations' in iteration 1
```

**Root cause**: `parse_design_document()` validated against the full 7-section `DesignSection` enum, but PI-001's calibration intentionally used a reduced 5-section set. The parser logged spurious warnings.

**Fix applied**: `parse_design_document()` now accepts `expected_sections` and validates only those.

---

### A-10: OpenTelemetry Export Failures (No Collector Running)

**Phase**: All  
**Severity**: Low  
**Status**: Fixed

**Symptom**:
```
WARNING [opentelemetry.exporter.otlp.proto.grpc.exporter] Transient error StatusCode.UNAVAILABLE
ERROR [opentelemetry.exporter.otlp.proto.grpc.exporter] Failed to export traces to localhost:4317
```

**Root cause**: OTLP exporter configured for `localhost:4317`, but no OTel collector was running.

**Impact**: No functional impact. Log noise and small latency from retries.

**Fix applied**: `STARTD8_OTEL=auto` now performs a connectivity check. If the endpoint is unreachable, OTLP is skipped with a single INFO message.

---

### A-11: Provider Registry Duplication Warnings

**Phase**: Startup  
**Severity**: Low  
**Status**: Fixed

**Symptom**:
```
WARNING [startd8.providers.registry] Overwriting existing provider: anthropic
WARNING [startd8.providers.registry] Overwriting existing provider: openai
```

**Root cause**: Entry points and built-in providers both registered the same providers.

**Fix applied**: `_register_builtin_providers()` skips registration when a provider is already present.

---

### A-12: Seed Lacks `_file_scope` and `file_ownership` — Defense Layers Are Hollow

**Phase**: Pipeline-wide  
**Severity**: High  
**Status**: In progress (export enrichment plan written)

**Symptom**: After implementing the defense-in-depth layers (Gate 2c, Smart Retry Gate, Review Guard), a dry run revealed that the current `artisan-context-seed.json` has no `_file_scope` or `file_ownership` data. All new defense code paths fall through to legacy behavior.

**Root cause**: The seed was generated from an older ContextCore export that pre-dates the `file_ownership` addition to `onboarding-metadata.json`. Plan ingestion never saw `file_ownership`, so it never derived `_file_scope`.

**Impact**: The defense-in-depth layers are structurally present but functionally inert. The seed must be regenerated from a fresh export to activate them.

**Resolution**: Re-run ContextCore export (with `file_ownership` now in `onboarding.py`), then re-run plan ingestion to produce a seed with `_file_scope`.

---

### A-13: Flat Design Calibration — All Tasks Get Same Depth Tier

**Phase**: Plan Ingestion  
**Severity**: Medium  
**Status**: In progress (plan written)

**Symptom**: Inspecting the artisan-context-seed.json showed that all tasks had identical `design_calibration` settings (same `depth_tier`, `max_output_tokens`, `sections`).

**Root cause**: `_derive_design_calibration` in plan ingestion uses only `estimated_loc` and an optional `SizeEstimator`. It does not consider artifact type. A ServiceMonitor generator (~30 LOC, brief) gets the same calibration as a Dashboard generator (~300 LOC, comprehensive).

**Impact**: Over-specced tasks waste tokens on unnecessary design sections. Under-specced tasks get truncated.

**Planned fix**: Use artifact type as a signal for calibration (ServiceMonitor → brief, Dashboard → comprehensive, PrometheusRule → standard).

---

### A-14: Missing Data in Seed — Derivation Rules, Coverage, Dependency Graph

**Phase**: Plan Ingestion (seed generation)  
**Severity**: Medium  
**Status**: In progress (export enrichment plan written)

**Symptom**: The artisan-context-seed.json is missing several high-value fields that exist in the ContextCore artifact manifest but are not surfaced in onboarding-metadata.json:
- `derivation_rules` (how business metadata maps to artifact properties)
- `coverage` gaps (which artifacts are "needed" vs. "exists")
- `artifact_dependency_graph` (generation ordering between artifacts)
- `resolved_artifact_parameters` (concrete values per artifact, not generic source pointers)
- `open_questions` (unresolved design questions from the context manifest)

**Root cause**: `build_onboarding_metadata()` in ContextCore's `onboarding.py` does not extract these fields from the artifact manifest model, even though the model contains them.

**Impact**: The DESIGN phase LLM must guess derivation mappings. The IMPLEMENT phase has no coverage awareness. Tasks are generated in arbitrary order rather than respecting artifact dependencies.

**Resolution**: Export enrichment plan at `/Users/neilyashinsky/Documents/dev/ContextCore/plans/EXPORT_ENRICHMENT_PLAN.md`.

---

## Part B: Issues From Other Sources

These issues are documented in existing files, workaround catalogs, and improvement suggestions. They were not necessarily observed first-hand in this session but are known Artisan/workflow issues.

---

### B-1: AST Merge Accumulation — Silent File Corruption Across Re-Runs

**Source**: DOWNSTREAM_WORKAROUND_CATALOG.md (W-004)  
**Status**: Fixed

Files grew from ~120 to 1078 lines across 3 re-runs because each AST merge added new definitions on top of existing ones. `loader.py` accumulated `PersonaDataLoader`, `PersonaLoader`, and standalone `load_roles()` from different runs.

**Fix**: `ASTMergeStrategy.merge()` now warns on >= 2x definition count inflation. New `merge_mode="replace"` option.

---

### B-2: SafeCodeGenerator Monkey-Patch Required for Token/Truncation Config

**Source**: DOWNSTREAM_WORKAROUND_CATALOG.md (W-001)  
**Status**: Fixed

`LeadContractorCodeGenerator` hardcoded `max_tokens=16384` and `fail_on_truncation=True`. Downstream projects had to subclass and monkey-patch `resolve_agent_spec` to override.

**Fix**: Constructor now accepts all four params. `resolve_agent_spec` accepts `**agent_config`.

---

### B-3: Post-Construction Size Limit Overrides Required

**Source**: DOWNSTREAM_WORKAROUND_CATALOG.md (W-002)  
**Status**: Fixed

`PrimeContractorWorkflow` hardcoded `max_lines_per_feature=150` and `max_tokens_per_feature=500`. Users had to override attributes post-construction.

**Fix**: Both are now constructor parameters.

---

### B-4: No Workspace Cleanup Method

**Source**: DOWNSTREAM_WORKAROUND_CATALOG.md (W-003)  
**Status**: Fixed

`--reset-state` only deleted the queue state JSON. Generated code, `.backup` files, and `__pycache__` persisted across re-runs.

**Fix**: `PrimeContractorWorkflow.clean_workspace()` method added.

---

### B-5: Relative `target_files` Path ValueError

**Source**: DOWNSTREAM_WORKAROUND_CATALOG.md (W-005)  
**Status**: Fixed

`integrate_feature()` called `target_path.relative_to(project_root)` which raised `ValueError` when `target_files` were relative strings.

**Fix**: `integrate_feature()` resolves relative paths. `_rel_display()` helper added.

---

### B-6: `WorkflowResult.from_error()` Returns None Metrics

**Source**: DOWNSTREAM_WORKAROUND_CATALOG.md (W-006)  
**Status**: Fixed

Downstream projects used triple-defense patterns (`hasattr` / `getattr` / `try-except`) to access `result.metrics` because `from_error()` passed `metrics=None`.

**Fix**: `from_error()` now uses `metrics or WorkflowMetrics()`.

---

### B-7: Missing `model` Field on `WorkflowMetrics`

**Source**: DOWNSTREAM_WORKAROUND_CATALOG.md (W-007)  
**Status**: Fixed

`WorkflowMetrics` had no `model` field, but downstream code accessed `result.metrics.model`.

**Fix**: Added `model: str = ""` to `WorkflowMetrics`.

---

### B-8: Markdown Code Fence Stripping Not Public

**Source**: DOWNSTREAM_WORKAROUND_CATALOG.md (W-009)  
**Status**: Fixed

Generated code arrived wrapped in markdown fences. The stripping logic was private.

**Fix**: Extracted to `startd8.utils.code_extraction.extract_code_from_response()`.

---

### B-9: No Pre-Integration Truncation Check

**Source**: DOWNSTREAM_WORKAROUND_CATALOG.md (W-010)  
**Status**: Fixed

Truncation detection ran during drafting but not during file integration. Truncated code could corrupt target files.

**Fix**: `integrate_feature()` now calls `detect_truncation()` before merging.

---

### B-10: Constraint Pre-Flight Does Not Abort

**Source**: IMPROVEMENT_SUGGESTIONS_CLARIFICATIONS.md (Item 10)  
**Status**: Open

The PLAN phase logs a warning when `preflight_failures > 0` but does not abort. Manifest constraints with `severity: blocking` that produce `CheckStatus.FAIL` are informational only.

**Recommendation**: Add `--abort-on-preflight-fail` for PLAN, and/or a pre-IMPLEMENT re-check.

---

### B-11: No `artifact_types_addressed` Per Task

**Source**: IMPROVEMENT_SUGGESTIONS_2026-02-12.md (Item 2)  
**Status**: Open

Task config has `feature_id`, `target_files`, `estimated_loc` but no `artifact_types_addressed`. Generators don't know which artifact types the task handles.

---

### B-12: No Seed Schema Validation on Output

**Source**: IMPROVEMENT_SUGGESTIONS_2026-02-12.md (Item 6)  
**Status**: Open

`atomic_write_json` writes the seed without schema validation. `WorkflowBase` validates input config schema but not output.

---

### B-13: No `design-handoff.json` Schema Documentation

**Source**: IMPROVEMENT_SUGGESTIONS_2026-02-12.md (Item 13)  
**Status**: Open

`HandoffData` has a dataclass structure and basic key validation, but no formal JSON schema or documentation.

---

### B-14: No Context File List or Checksums in Handoff

**Source**: IMPROVEMENT_SUGGESTIONS_2026-02-12.md (Item 14)  
**Status**: Addressed (Phase 4)

The design handoff now includes a `context_files` list with SHA-256 checksums computed at write time. The implementation phase validates these checksums on load and warns (or fails, with `--strict-handoff`) if drift is detected.

---

### B-15: No Shared Schema Version Across Pipeline Artifacts

**Source**: IMPROVEMENT_SUGGESTIONS_2026-02-12.md (Item 15)  
**Status**: Open

The seed has `version: "1.0.0"`, the handoff has `schema_version: 1`, and the artifact manifest has its own version. There is no unified version for compatibility branching.

---

### B-16: Incomplete Provenance Chain

**Source**: IMPROVEMENT_SUGGESTIONS_2026-02-12.md (Item 16), PLAN_INGESTION_CONTEXTCORE_RECOMMENDATIONS.md  
**Status**: Addressed (Phase 2 + Phase 3)

`source_checksum` is now propagated end-to-end: export → onboarding → plan ingestion seed → PLAN phase context → FINALIZE generation-manifest.json. Phase 2 added extraction in PLAN and recording in FINALIZE. Phase 3 added verification of `source_checksum` against `.contextcore.yaml` at the ingestion preflight boundary, with structured evidence in `preflight-report.json`.

---

### B-17: No Export Contract Preflight at Ingestion Boundary

**Source**: PLAN_INGESTION_CONTEXTCORE_RECOMMENDATIONS.md (Recommendation 2)  
**Status**: Addressed (Phase 3)

`_preflight_export_contract()` validates: expected export files present, checksum integrity (artifact manifest + project context + source_checksum vs `.contextcore.yaml`), parameter source resolvability summary, and coverage minimum. Hard failures cause immediate workflow abort. Phase 3 added `source_checksum` verification against the actual `.contextcore.yaml` and a structured `preflight-report.json` artifact for downstream gating.

---

### B-18: No Traceability Artifact From Ingestion

**Source**: PLAN_INGESTION_CONTEXTCORE_RECOMMENDATIONS.md (Recommendation 6)  
**Status**: Addressed (Phase 3)

`ingestion-traceability.json` is emitted on every successful run with: requirement → feature → task mappings, artifact → feature → task mappings, unresolved entries with severity, translation quality metrics, checksum evidence, and optional `refine_impact` showing before/after metrics when CRP refinement is applied. Prime YAML tasks are also enriched with `requirement_ids`, `acceptance_obligations`, and `source_references`.

---

### B-19: Loki Rules Missing Derivation Rules in Artifact Manifest

**Source**: Analysis of `manifest_v2.py` during this session  
**Status**: Open (in export enrichment plan)

Six of seven artifact types have `derived_from` rules populated in `generate_artifact_manifest()`. Loki rules do not. This means Loki rules have no derivation audit trail.

---

## Summary

| Category | Count | Fixed/Addressed | Open | In Progress |
|----------|-------|----------------|------|-------------|
| **Session (A-series)** | 14 | 4 | 4 | 6 |
| **Other sources (B-series)** | 19 | 12 | 7 | 0 |
| **Total** | 33 | 16 | 11 | 6 |

### Priority Next Actions

1. **Re-run ContextCore export** with enriched `onboarding-metadata.json` to activate defense layers (A-12, A-14)
2. **Re-run plan ingestion** to produce a seed with `_file_scope`, coverage, and artifact-aware calibration (A-13)
3. **Build PI-001** with `--adopt-prior` using the new seed
4. **Add `--fail-on-review-failure` option** (A-2)
