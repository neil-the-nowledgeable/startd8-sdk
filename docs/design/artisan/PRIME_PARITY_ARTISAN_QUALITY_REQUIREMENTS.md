# Prime-Parity Artisan Quality Requirements

**Version:** 1.0.0  
**Created:** 2026-02-26  
**Status:** Draft  
**Tracking prefix:** REQ-PAQ  
**Scope:** Raise Artisan design/output quality to Prime parity by reducing harmful complexity and enforcing deterministic prompt, review, and quality-gate behavior.

## Objective

Artisan quality is currently less reliable than Prime in complex runs. This document defines requirements to close that gap using six proven lessons:

1. Deterministic context budgets and precedence.
2. Mandatory re-review after revision.
3. Canonical production path with controlled variants.
4. Explicit quality gate semantics.
5. Smaller, higher-signal context surface.
6. Full observability for prompt/review/gate outcomes.

## Problem Statement

Prime quality benefits from deterministic prompt assembly, bounded context sections, and tighter acceptance controls. Artisan has richer context and more branches, but quality can regress due to:

- Multiple execution paths (`use_modular_prompts` vs dual-review path).
- Acceptance paths that can return revised output without another full dual review.
- Broad context surfaces where low-signal metadata competes with constraints.
- Quality gates focused on TEST/REVIEW while DESIGN quality failures can pass through.
- Limited telemetry for section drops, disagreement resolution outcomes, and path-level quality impact.

## Requirements

### Layer 1: Deterministic Budgeting and Precedence (REQ-PAQ-1xx)

#### REQ-PAQ-100: Section Budget Registry for Design Prompt Assembly [P0]

**Implementation targets:**  
`src/startd8/contractors/prompt_utils.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`

Define a static, versioned budget registry for design prompt sections with explicit per-section character caps and required/optional semantics.

**Acceptance criteria:**
1. A module-level budget config exists with explicit caps for at least: requirements, architectural context, critical parameters, dependency designs, and supporting metadata.
2. A deterministic truncation marker is applied whenever any section is clipped.
3. Budget values are logged in task-level telemetry for every design generation.

#### REQ-PAQ-101: Deterministic Compression Order with Non-Droppable Tier-0 [P0]

**Implementation targets:**  
`src/startd8/contractors/prompt_utils.py`

Enforce deterministic compression order where Tier-0 constraints are never dropped.

**Acceptance criteria:**
1. Compression order is deterministic and documented (for example: T3 drop -> T2 collapse -> T1 truncate).
2. Tier-0 keys are always emitted in output, even under extreme budget pressure.
3. If any Tier-0 key is unavailable, output includes an explicit `MISSING_T0` marker for that key.

#### REQ-PAQ-102: Prompt Budget Enforcement Across DESIGN, IMPLEMENT, REVIEW [P1]

**Implementation targets:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_phases/development.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`

Apply budget enforcement patterns consistently across DESIGN, IMPLEMENT, and REVIEW prompt assembly to avoid phase-specific drift.

**Acceptance criteria:**
1. Each phase records final prompt size and section-level contributions.
2. Each phase emits a warning when truncation occurs.
3. Each phase follows a documented precedence order for dropped/condensed context fields.

### Layer 2: Review Convergence Integrity (REQ-PAQ-2xx)

#### REQ-PAQ-200: Mandatory Dual Re-Review After Any Revision [P0]

**Implementation targets:**  
`src/startd8/contractors/artisan_phases/design_documentation.py`

A revised design must not be accepted until reviewer and arbiter re-evaluate the revised version.

**Acceptance criteria:**
1. After `_revise_design(...)`, both reviewer and arbiter are run again on the revised document.
2. `DesignDocumentResult` verdicts always correspond to the final returned design text.
3. No return path exists where a revised design is returned without post-revision review evidence.

#### REQ-PAQ-201: Final Acceptance Depends on Latest Review Pair [P0]

**Implementation targets:**  
`src/startd8/contractors/artisan_phases/design_documentation.py`

Final acceptance/rejection must be based only on the latest reviewer+arbiter verdict pair, not pre-revision verdicts.

**Acceptance criteria:**
1. `agreed=True` requires both latest verdicts to approve and no unresolved structural disagreement.
2. `agreed=False` includes machine-readable reason codes (for example: `DISAGREEMENT_UNRESOLVED`, `CONFIDENCE_TOO_LOW`, `MAX_ITERATIONS_EXCEEDED`).
3. Result metadata stores the iteration index that produced the final accepted design.

#### REQ-PAQ-202: Resolution Actions Must Be Auditable [P1]

**Implementation targets:**  
`src/startd8/contractors/artisan_phases/design_documentation.py`  
`src/startd8/contractors/forensic_log.py`

Every disagreement resolution decision must leave structured evidence of what changed and why.

**Acceptance criteria:**
1. Resolution action, guidance, and deciding actor are persisted in result metadata.
2. When revision is requested, a structured delta summary is stored.
3. Forensic logs include resolution action counts and outcomes per run.

### Layer 3: Canonical Path Governance (REQ-PAQ-3xx)

#### REQ-PAQ-300: Canonical Production Design Path [P0]

**Implementation targets:**  
`src/startd8/contractors/context_seed_handlers.py`

Define one canonical production path for DESIGN quality (dual-review convergence path) and make alternates explicit experimental routes.

**Acceptance criteria:**
1. Default production configuration resolves to a single canonical path.
2. Non-canonical paths require explicit opt-in via config/CLI.
3. Run metadata records the chosen path for each task.

#### REQ-PAQ-301: Variant Path Must Not Bypass Quality Envelope [P0]

**Implementation targets:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`

If a modular/single-pass variant path is used, it must still pass through a review envelope equivalent to production quality checks.

**Acceptance criteria:**
1. Variant path output is reviewed by reviewer+arbiter (or equivalent stricter validator) before acceptance.
2. Variant path cannot hardcode `agreed=True` without evidence-based review.
3. Failed review in variant path follows the same blocking/warning policy as canonical path.

#### REQ-PAQ-302: Route Selection Policy by Complexity and Risk [P1]

**Implementation targets:**  
`src/startd8/contractors/context_seed_handlers.py`

Route selection must be policy-driven, not ad hoc.

**Acceptance criteria:**
1. Route-selection policy uses explicit criteria (complexity, contested files, dependency density, edit mode).
2. Policy decisions are logged with criterion values.
3. A kill switch can force all tasks through canonical path.

### Layer 4: Quality Gate Semantics (REQ-PAQ-4xx)

#### REQ-PAQ-400: Design Gate Metrics and Thresholds [P0]

**Implementation targets:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_contractor.py`

Introduce explicit DESIGN quality gate metrics.

**Acceptance criteria:**
1. DESIGN phase output includes `total_failed` and `agreement_rate` (or equivalent canonical metrics).
2. Metrics are computed from per-task results and are deterministic.
3. Thresholds are configurable and documented.

#### REQ-PAQ-401: Include DESIGN in Global Quality Gate Enforcement [P0]

**Implementation targets:**  
`src/startd8/contractors/artisan_contractor.py`

Global gate policy (`skip`/`warn`/`block`) must apply to DESIGN in addition to TEST and REVIEW.

**Acceptance criteria:**
1. `_check_quality_gate(...)` evaluates DESIGN failures using phase output metrics.
2. In `block` mode, failing DESIGN gate raises a blocking exception.
3. In `warn` mode, failing DESIGN gate emits structured warning details.

#### REQ-PAQ-402: Contract-Level DESIGN Exit Quality Rules [P1]

**Implementation targets:**  
`src/startd8/contractors/artisan-pipeline.contract.yaml` (or canonical contract YAML path)  
`src/startd8/contractors/context_schema.py`

Add DESIGN exit quality checks to contract validation.

**Acceptance criteria:**
1. DESIGN exit contract defines quality extractors for failure and agreement metrics.
2. Violations are surfaced through boundary validation result structures.
3. Violations appear in forensic artifacts and run summaries.

### Layer 5: Context Surface Simplification (REQ-PAQ-5xx)

#### REQ-PAQ-500: Shared Tier Registry Across Design-Adjacent Prompts [P0]

**Implementation targets:**  
`src/startd8/contractors/prompt_utils.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`  
`src/startd8/contractors/context_seed_handlers.py`

Use one tier registry and one rendering policy for design-adjacent context to reduce drift and prompt bloat.

**Acceptance criteria:**
1. Tier classification is single-source and imported by all participating assemblers.
2. Unknown keys default to a non-critical tier.
3. Tier changes are traceable and versioned.

#### REQ-PAQ-501: Enforce High-Signal Minimum Context [P0]

**Implementation targets:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`

Require a minimal high-signal context set for design generation.

**Acceptance criteria:**
1. Required context includes task requirements, architecture constraints, and critical parameter checklist (or explicit missing markers).
2. Generation is blocked or downgraded when required high-signal context is absent.
3. Missing high-signal fields are included in phase output diagnostics.

#### REQ-PAQ-502: De-Duplication and Overflow Quarantine [P1]

**Implementation targets:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/prompt_utils.py`

Prevent duplicate rendering of semantically identical context and quarantine overflow into concise summaries.

**Acceptance criteria:**
1. A field cannot appear in both dedicated section and generic blob in the same prompt.
2. Overflow data is summarized into deterministic one-line references.
3. Prompt logs include dropped/condensed field names.

### Layer 6: Telemetry and Forensics (REQ-PAQ-6xx)

#### REQ-PAQ-600: Prompt Assembly Telemetry [P0]

**Implementation targets:**  
`src/startd8/contractors/artisan_phases/design_documentation.py`  
`src/startd8/contractors/context_seed_handlers.py`

Emit structured telemetry for prompt composition.

**Acceptance criteria:**
1. Per-task telemetry includes total prompt chars/tokens and per-section contributions.
2. Telemetry includes truncation events and dropped field counts.
3. Walkthrough mode persists prompt diagnostics artifacts under `.startd8/walkthrough`.

#### REQ-PAQ-601: Review Disagreement Telemetry [P0]

**Implementation targets:**  
`src/startd8/contractors/artisan_phases/design_documentation.py`  
`src/startd8/contractors/forensic_log.py`

Emit structured disagreement and resolution telemetry.

**Acceptance criteria:**
1. Per-task telemetry records disagreement count, categories, and confidence gap.
2. Resolution decisions include action type, iteration, and outcome.
3. Run-level aggregates include disagreement rate and re-review rate.

#### REQ-PAQ-602: Path-Quality Correlation Metrics [P1]

**Implementation targets:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/forensic_log.py`

Track quality outcomes by path type to validate canonical-path assumptions.

**Acceptance criteria:**
1. Each task records `prompt_version`/path tag and quality outcome.
2. Run summary includes quality metrics grouped by path.
3. Metrics support direct comparison across canonical vs variant paths.

#### REQ-PAQ-603: Gate Outcome Traceability [P1]

**Implementation targets:**  
`src/startd8/contractors/artisan_contractor.py`  
`src/startd8/contractors/forensic_log.py`

Quality gate outcomes must be traceable from phase output through final run summary.

**Acceptance criteria:**
1. Gate outcomes include phase, policy mode, threshold, observed value, and decision.
2. Final workflow summary includes a quality gate section listing all violations.
3. Contract and runtime gate signals use consistent identifiers.

## Verification Requirements

### REQ-PAQ-700: Prime-Parity Evaluation Harness [P0]

**Implementation targets:**  
`scripts/` benchmark runner and/or existing workflow test harnesses  
`docs/` benchmark result templates

Define a repeatable benchmark comparing Artisan against Prime on the same seed set.

**Acceptance criteria:**
1. Fixed benchmark suite contains representative simple, medium, and high-complexity seeds.
2. Comparison report includes at least: review pass rate, failed-task rate, design agreement rate, and truncation incidence.
3. Results are published as versioned artifacts for every major change.

### REQ-PAQ-701: Rollout Guardrails [P1]

**Implementation targets:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_contractor.py`

Ship improvements with controlled rollout and immediate rollback capability.

**Acceptance criteria:**
1. Feature flags exist for major behavior changes (re-review enforcement, canonical-only routing, design gate blocking).
2. Flags default to safe production behavior and are reversible without code edits.
3. Rollout plan defines canary cohort and rollback triggers.

## Traceability Matrix

| Prime lesson to apply | Covered by requirements |
|---|---|
| Hard budgets + deterministic precedence | REQ-PAQ-100, 101, 102 |
| Re-review after revision | REQ-PAQ-200, 201, 202 |
| Canonical production path | REQ-PAQ-300, 301, 302 |
| Explicit quality gate semantics | REQ-PAQ-400, 401, 402, 603 |
| Constrain context surface | REQ-PAQ-500, 501, 502 |
| Better observability | REQ-PAQ-600, 601, 602 |

## Related Documents

- `docs/design/artisan/ARTISAN_REQUIREMENTS.md`
- `docs/design/artisan/PROJECT_CENTRIC_ARTISAN_REQUIREMENTS.md`
- `docs/design/artisan/DESIGN_PROMPT_TIERED_CONTEXT_REQUIREMENTS.md`
- `docs/design/prime/PRIME_PROMPT_ARTISAN_PATTERNS_IMPLEMENTATION.md`
- `docs/PRIME_CONTRACTOR_WORKFLOW_GUIDE.md`

