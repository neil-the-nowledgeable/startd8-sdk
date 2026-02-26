# Phase 5 Extension: Prime Contractor Forward Manifest Validator

**Version:** 1.0.0
**Created:** 2026-02-26
**Status:** Draft
**Extends:** [Phase_5_Validator_Requirements.md](Phase_5_Validator_Requirements.md)
**Context:** Phase 5 introduced the `validate_forward_manifest` engine to enforce Forward Manifest interface contracts, but only integrated it into the Artisan (`ReviewPhaseHandler`) pipeline. This document defines the requirements for integrating the validator into the Prime Contractor (`LeadContractorWorkflow`).

---

## 1. Goal Description

Enable the Prime Contractor's `LeadContractorWorkflow` to enforce structural compliance against the `ForwardManifest` during its internal Drafter-Lead review iterations. By invoking the `validate_forward_manifest` engine during the `_review_draft` stage, the Lead Contractor can automatically detect structural drift (e.g., missing specific function names, failed class ancestry, missing required files) and translate these programmatic `ContractViolation` instances into explicit, auto-failing `[BLOCKING]` issues for the Drafter to fix in the next iteration.

---

## 2. Requirements

### 2.1 Pass Forward Manifest into Lead Contractor Execution (REQ-PC-VAL-001)

**Requirement:** The `PrimeContractorWorkflow` must pass the `forward_manifest` down to the `LeadContractorWorkflow` so it is available during the draft review cycle.

**Implementation:**

- `LeadContractorWorkflow._execute()` accepts a `config` dictionary.
- `PrimeContractorWorkflow` must ensure `forward_manifest` is included in this `config` dictionary (specifically, the `config["context"]` block) before invoking `lead.run()`.

---

### 2.2 Reconstruct ManifestRegistry for the Draft (REQ-PC-VAL-002)

**Requirement:** The validation engine requires a `ManifestRegistry` built from the generated codebase, but in the `LeadContractorWorkflow`, the "codebase" is represented as in-memory code blocks inside the `DraftResult`, not physical files on disk.

**Implementation:**

- In `LeadContractorWorkflow._review_draft()`, intercept the Drafter's output before or during Lead review.
- Parse the multi-file markdown blocks from `draft.raw_draft` into an ephemeral `FileManifest` mapping.
- Construct a temporary `ManifestRegistry` from these parsed definitions to represent the exact state of the Drafter's current proposal.

---

### 2.3 Validator Hook during Review (REQ-PC-VAL-003)

**Requirement:** The `LeadContractorWorkflow` must conditionally execute `validate_forward_manifest` if a `forward_manifest` is present in the task context.

**Implementation:**

- After creating the temporary `ManifestRegistry` (REQ-PC-VAL-002), query `config["context"].get("forward_manifest")`.
- If the manifest exists and contains applicable contracts, invoke `validate_forward_manifest(manifest, registry)`.
- If violations are found with `severity="error"`, they must be captured for injection into the review results.

---

### 2.4 Auto-Fail on Structural Violations (REQ-PC-VAL-004)

**Requirement:** If the validator detects `error`-severity contract violations, the current `ReviewResult` must be forcefully failed (`passed=False`), regardless of the LLM Lead Architect's sentiment.

**Implementation:**

- During `_review_draft()`, if `ContractViolation` errors exist, override the Lead Agent's `ReviewResult.passed` flag to `False`.
- Prepend or append the structured `ContractViolation` descriptions directly into the `ReviewResult.issues` list, explicitly marking them as `[BLOCKING]` so the Drafter understands they are non-negotiable structural requirements.
- Ensure the `ReviewResult.score` is capped or penalized (e.g., forced below the `pass_threshold`).

---

## 3. Proposed Changes Summary

| Component | Change |
|-----------|--------|
| `prime_contractor.py` | Ensure `forward_manifest` is injected into the `config["context"]` passed to `LeadContractorWorkflow._execute`. |
| `lead_contractor_workflow.py` | Update `_review_draft` to parse the draft into a temporary `ManifestRegistry`, run `validate_forward_manifest`, and override the `ReviewResult` on error. |
| `tests/unit/contractors/test_lead_contractor_workflow.py` | Add a unit test isolating `_review_draft`, mocking `validate_forward_manifest` to return an error, and asserting `passed=False` with the injected `[BLOCKING]` issue. |

---

## 4. Verification Plan

1. **Unit Test:** Isolate the `_review_draft` method inside `LeadContractorWorkflow`. Provide it with a context containing a mock `forward_manifest`. Mock `validate_forward_manifest` to yield one `ContractViolation`. Assert the returned `ReviewResult` has `passed=False` and the issue list contains the violation text.
2. **Integration Test:** Run a full Prime Contractor iteration where the `forward_manifest` specifies a specific function name (`my_specific_pipeline_trigger`), but the Drafter's output omits it. Assert that the Lead Contractor review catches this, fails the iteration, and the Drafter includes it on iteration 2 before the loop successfully exits.
