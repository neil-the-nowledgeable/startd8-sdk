# Artisan Workflow Testing Issues: Session-First and External Sources

## Purpose

Provide a single, session-aware issue summary for Artisan workflow testing with two explicit sections:

1. Issues and implications identified in this current session
2. Additional known issues from other documented sources

---

## Part 1: Issues and Implications Identified in This Session

Note: In this session we did not execute a fresh Artisan run directly. The items below are issues/risks identified during workflow and design analysis, especially around plan-ingestion -> artisan handoff quality.

### S1-1. Plan-ingestion is still primarily plan-text-first

- Current ingestion requires `plan_path` and reads it as text.
- ContextCore export artifacts and requirements are not first-class required inputs.
- Impact on Artisan: weaker seed quality, more downstream guessing in DESIGN/IMPLEMENT.

### S1-2. Requirements-aware dual-document review is available but under-leveraged by ingestion

- `architectural_review_log` supports `feature_requirements`, but ingestion refine flow does not fully treat requirements as a first-class review input path.
- Impact on Artisan: weaker requirements traceability before implementation starts.

### S1-3. Boundary validation gaps before Artisan execution

- No strict pre-ingestion gate for export completeness/integrity (expected files, checksum chain, resolvability, coverage readiness).
- Impact on Artisan: stale or incomplete upstream contracts can enter seed generation and fail late.

### S1-4. Missing explicit translation fidelity checks

- Ingestion currently lacks a hard check that all required artifacts/requirements are mapped into transformed tasks/features.
- Impact on Artisan: task omissions and partial coverage may only surface during later phases.

### S1-5. Routing logic can be improved with quality signals

- Route decision is complexity-based; it does not strongly incorporate translation quality indicators (coverage, mapping completeness, conflict count).
- Impact on Artisan: plans with low translation fidelity may still route in ways that increase rework.

### S1-6. Traceability artifact not emitted as first-class output

- No dedicated ingestion traceability file that links requirements + artifacts -> tasks with unresolved/conflict diagnostics.
- Impact on Artisan: harder root-cause analysis when phases fail or outputs are incomplete.

### S1-7. ContextCore contract hardening is warranted (without tight coupling)

- ContextCore can improve downstream reliability by strengthening schemas, identity fields, and validation reporting.
- This can remain decoupled if ContextCore stays focused on specification/contract output, not Prime/Artisan runtime semantics.

---

## Part 2: Additional Known Issues From Other Sources

Primary references:

- `docs/ARTISAN_WORKFLOW_ISSUES_CATALOG.md`
- `docs/ARTISAN_PI-001_RUN_ISSUES.md`
- `docs/PLAN_INGESTION_CONTEXTCORE_RECOMMENDATIONS.md`

### E2-1. Multi-file split failures in IMPLEMENT

- LLM can consolidate multi-file tasks into one file, omitting required companion files.
- Auto-stub fallback prevents hard failure but can mask generation failure quality.

### E2-2. Review threshold mismatch with final status

- REVIEW can fail quality threshold while workflow still reports overall success.
- Risk: false confidence in production readiness without a fail-on-review policy.

### E2-3. Generation cache/adopt-prior behavior can replay failures

- Prior failed generation results can be re-adopted and reused.
- Risk: repeated bad outcomes unless cache/state is reset or filtering is improved.

### E2-4. Design token truncation and section mismatch warnings

- Long design outputs can truncate at configured token caps.
- Parser warnings may flag missing sections that were intentionally excluded by calibration tiers.

### E2-5. Seed fidelity gaps reduce downstream execution quality

- Missing or weak seed fields in some runs: file ownership/scope, derivation context, coverage awareness, dependency richness.
- Risk: DESIGN/IMPLEMENT phases compensate heuristically and become less deterministic.

### E2-6. Provenance and checksum chain not always enforced as circuit-breakers

- Checksum propagation exists in parts of pipeline, but hard-stop validation across boundaries is not uniformly enforced.
- Risk: stale or hand-edited upstream data can flow through to Artisan.

### E2-7. Observability/environment noise during test runs

- OTLP endpoint unavailability and provider duplicate-registration warnings create noisy logs.
- Risk: reduced signal-to-noise during troubleshooting.

### E2-8. Configuration and integration friction points

- Historical issues include path handling pitfalls, output directory mismatches, and metric-model edge cases.
- Risk: avoidable test instability and extra debugging time.

---

## Consolidated Near-Term Actions

1. Add ingestion preflight gates for export integrity and coverage readiness.
2. Treat requirements and ContextCore export artifacts as first-class ingestion inputs.
3. Emit an ingestion traceability artifact and enforce mapping completeness checks.
4. Add optional fail-on-review-failure behavior for stronger quality policy.
5. Improve seed richness (coverage, ownership/scope, dependency context) before Artisan run.

---

## Notes on Scope

This file focuses on known testing issues and operational quality risks. It does not replace detailed per-issue runbooks in the referenced docs.
