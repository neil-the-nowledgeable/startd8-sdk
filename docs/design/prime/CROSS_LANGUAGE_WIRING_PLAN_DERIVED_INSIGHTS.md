# Plan-Derived Insights — Cross-Language Wiring Gap Requirements

> **Version:** 1.0.0
> **Date:** 2026-03-23
> **Status:** REVIEW
> **Parent Plan:** [CROSS_LANGUAGE_WIRING_GAP_PLAN.md](CROSS_LANGUAGE_WIRING_GAP_PLAN.md)
> **Parent Audit:** [CROSS_LANGUAGE_WIRING_GAP_AUDIT.md](CROSS_LANGUAGE_WIRING_GAP_AUDIT.md)
> **Affected Requirements:**
>   - [KAIZEN_PRIME_REQUIREMENTS.md](KAIZEN_PRIME_REQUIREMENTS.md) (Layers 1, 5)
>   - [MULTI_LANGUAGE_PARITY_REQUIREMENTS.md](MULTI_LANGUAGE_PARITY_REQUIREMENTS.md) (Sections 2-4)
>   - [LANGUAGE_AGNOSTIC_REFACTOR_REQUIREMENTS.md](LANGUAGE_AGNOSTIC_REFACTOR_REQUIREMENTS.md) (Sections 3.4, 4)
>   - [KAIZEN_NODEJS_REQUIREMENTS.md](../prime-contractor-node/KAIZEN_NODEJS_REQUIREMENTS.md) (Sections 2-5)

---

## Purpose

Implementation planning for the wiring gap audit exposed 7 structural blind spots in the existing requirements. These are not missing features — they are assumptions baked into how the requirements are organized that prevented the gaps from being visible until implementation was planned end-to-end.

This document captures those insights, proposes specific requirements amendments, and identifies quick wins that only became visible through the planning lens.

---

## Insight 1: Requirements Treat Languages as Independent — The Pipeline Doesn't

### What the requirements assume

KAIZEN_NODEJS_REQUIREMENTS.md, MULTI_LANGUAGE_PARITY_REQUIREMENTS.md, and the language-specific sections all describe each language as a self-contained capability stack: "implement semantic checks for Java", "add repair steps for Go", "wire Node.js into the pipeline." Each language has its own requirements document, its own status dashboard, its own verification strategy.

### What planning revealed

The pipeline is not a set of independent language stacks — it's a **shared backbone** (integration engine → disk compliance → quality scoring → postmortem → Kaizen suggestions → prompt injection) with **language-specific plugins** at each stage. The wiring gaps are almost entirely at the boundary between plugin and backbone:

- The backbone calls `_run_semantic_checks()` but the backbone itself doesn't have a Python branch (C-1)
- The backbone collects `DiskComplianceResult.semantic_issues` but the backbone's scoring formula is language-blind (M-1)
- The backbone injects Kaizen hints into prompts but the backbone never extracts `coding_standards` from the language profile (H-2)

**No requirements document specifies the backbone's responsibilities to language plugins.** Each language doc says "implement check X" but none say "verify the backbone dispatches to X" or "verify the backbone scores X's output correctly."

### Proposed amendment

**Add a new section to KAIZEN_PRIME_REQUIREMENTS.md:** "Layer 0 — Language Backbone Contract"

This layer would specify:

| Backbone Obligation | Requirement |
|---------------------|-------------|
| **Dispatch completeness** | `_run_semantic_checks()` SHALL have a branch for every language in `_EXT_TO_LANGUAGE`. Adding a language without a dispatch branch is a requirements violation. |
| **Collection completeness** | Every file type validated by `_validate_non_python_file()` SHALL have its semantic issues collected into `DiskComplianceResult.semantic_issues`. |
| **Scoring universality** | `compute_disk_quality_score()` SHALL accept a `language_id` parameter and use language-appropriate severity weights. |
| **Prompt injection universality** | `spec_builder.py` SHALL extract and inject `language_profile.coding_standards` for ALL languages. A language profile without its standards in the prompt is a wiring violation. |
| **Kaizen suggestion completeness** | Every semantic check category SHALL have an entry in `_SEMANTIC_CATEGORY_TO_SUGGESTION`. A check that fires without a suggestion mapping is a wiring violation. |

**Verification:** Add a cross-language integration test that iterates all 5 languages and verifies end-to-end: semantic check → collection → scoring → suggestion → prompt injection. This single test would have caught all 15 gaps in the audit.

### Why this matters

Without this backbone contract, each new language will repeat the same wiring gaps. C# was added and immediately had 5 orphaned semantic checks. Node.js was added and TypeScript was silently skipped. The pattern will continue for every future language unless the backbone's obligations are specified.

---

## Insight 2: The "Primary Language" Assumption Created a Blind Spot

### What the requirements assume

MULTI_LANGUAGE_PARITY_REQUIREMENTS.md Section 1 establishes Python as the "Reference Implementation" and grades all other languages against it. The implicit assumption: Python is fully wired, other languages need to catch up.

### What planning revealed

Python is the **least wired language** at 40% completion. It has:
- 4 semantic checks that never execute (orphaned code)
- 0/4 Kaizen suggestion mappings
- No integration engine branch (the only language skipped!)
- Repair routes that use `language=None` (accidental fallthrough)

The parity matrix (Section 2) grades Go/Java/Node.js/C# against Python's semantic checks — but Python's semantic checks don't actually run. The matrix is grading other languages against a phantom baseline.

### What specifically went wrong

The Python semantic validation was refactored from `semantic_checks.py` (4 simple checks) to `validate_disk_compliance()` (10-layer suite). The 10-layer suite runs during postmortem but was never wired into the integration engine. The old 4 checks were never deleted, but they were never integrated into the new path either. Both systems exist; neither runs at integration time.

The MULTI_LANGUAGE_PARITY_REQUIREMENTS.md was written after the refactor, but it references `semantic_checks.py` (the old system) as the baseline. Nobody noticed the old system was orphaned because the requirements assumed the primary language was complete.

### Proposed amendment

**Update MULTI_LANGUAGE_PARITY_REQUIREMENTS.md Section 1.2** to add a verification column:

| Check | Function | What It Detects | **Verified Running?** |
|-------|----------|----------------|-----------------------|
| `check_duplicate_main_guards` | `semantic_checks.py:32` | Multiple `if __name__ == "__main__"` | **NO — orphaned, never called** |
| ... | ... | ... | ... |

**Add REQ-MLP-BASELINE:** "Before grading other languages against the Python baseline, verify that every Python capability listed in Section 1 is actively exercised in the production pipeline. A capability that exists as dead code is NOT a baseline — it is a gap."

**Add a CI check:** A test that imports `semantic_checks.run_semantic_checks` and greps for call sites. If zero call sites exist, the test fails — preventing silent orphaning.

---

## Insight 3: Requirements Specify "Add Check" Without Specifying "Wire Check"

### What the requirements assume

Every language-specific requirements document (KAIZEN_NODEJS_REQUIREMENTS, MULTI_LANGUAGE_PARITY_REQUIREMENTS Sections 3.1-3.4) specifies checks to implement:

> "Implement `check_empty_catch_blocks` in `validators/java_semantic_checks.py`"
> "Implement `check_var_usage` in `validators/nodejs_semantic_checks.py`"

The implicit assumption: implementing the check function is sufficient. The pipeline will discover and use it.

### What planning revealed

Implementing a check function is ~20% of making it effective. The full pipeline requires 5 wiring points:

```
1. Implement check function          ← Requirements specify this
2. Wire into integration engine      ← Requirements silent
3. Wire into disk compliance         ← Requirements silent
4. Add _SEMANTIC_CATEGORY_TO_SUGGESTION mapping ← Requirements silent
5. Add repair routing (if repairable) ← Sometimes specified
```

The audit found that steps 2-4 are missing for multiple checks across every language. The checks exist, they even have tests, but they produce no downstream effect because the wiring is incomplete.

### Proposed amendment

**Add to KAIZEN_PRIME_REQUIREMENTS.md Layer 5 (Feedback Loop):**

> **REQ-KZ-510: Semantic Check Pipeline Completeness Invariant**
>
> Every semantic check category registered in any `validators/*_semantic_checks.py` module SHALL satisfy ALL of the following within the same release:
>
> 1. **Collection:** The check's output appears in `DiskComplianceResult.semantic_issues` when the file is validated
> 2. **Scoring:** The check's severity contributes to `compute_disk_quality_score()` via the `semantic_penalty` formula
> 3. **Suggestion mapping:** The check's category has an entry in `_SEMANTIC_CATEGORY_TO_SUGGESTION` that routes to a valid `CAUSE_TO_SUGGESTION` key
> 4. **Classification:** The check is explicitly classified as either REPAIRABLE (has repair route + step) or ADVISORY (intentionally no repair, documented reason)
>
> **Verification:** A unit test SHALL iterate all semantic check modules, extract emitted categories, and assert each satisfies points 1-3. Point 4 is verified by the presence of either a `_ROUTING_TABLE` entry OR a comment in `_REPAIRABLE_CATEGORIES` documenting the advisory classification.

**Update each language-specific requirements document** to use a 5-column implementation checklist for each new check:

| Check | Function | Collection | Suggestion | Classification |
|-------|----------|:---:|:---:|:---:|
| `check_var_usage` | `nodejs_semantic_checks.py` | `_validate_js_file()` | `var_usage` → `var_usage_detected` | REPAIRABLE → `var_to_const` |

This makes the wiring explicit and auditable.

---

## Insight 4: "Advisory" vs "Repairable" Is an Undocumented Decision

### What the requirements assume

KAIZEN_NODEJS_REQUIREMENTS.md REQ-KZ-ND-402b classifies categories as "Repairable" or "Advisory" — this is excellent. But it's the only requirements document that does this. The Java, Go, C#, and Python requirements don't distinguish between "we chose not to repair this" and "we haven't gotten to it yet."

### What planning revealed

The audit found 11 Java/C# semantic checks with no repair routes. Without the advisory/repairable classification, an implementer can't tell:
- Is `missing_override` (Java) unrepaired because nobody built the step yet? → Build it
- Is `module_system_mixing` (Node.js) unrepaired because repair requires human judgment? → Leave it
- Is `missing_async_await` (C#) unrepaired because it's too risky to auto-fix? → Document why

The planning process had to independently reason about each check's repairability. This reasoning should be in the requirements, not discovered during implementation.

### Proposed amendment

**Add to MULTI_LANGUAGE_PARITY_REQUIREMENTS.md Section 4.2 (Semantic Check Protocol):**

> **REQ-MLP-SEM-CLASS:** Every semantic check SHALL be classified at requirements time as one of:
>
> | Classification | Meaning | Pipeline Treatment |
> |---------------|---------|-------------------|
> | **REPAIRABLE** | A deterministic repair step can fix this issue | Must have repair route + step |
> | **ADVISORY** | Repair requires human judgment or architectural decision | Detection + Kaizen suggestion only; document WHY repair is infeasible |
> | **DEFERRED** | Repair is feasible but not yet implemented | Track as backlog with effort estimate |
>
> The classification SHALL appear in the requirements document, not just the code. The `_REPAIRABLE_CATEGORIES` set in `semantic_bridge.py` is the runtime enforcement, but the requirements are the source of truth for the classification decision.

**Retroactively classify all existing checks.** The planning process already produced this classification:

**Intentionally advisory (repair requires human decision):**
- `module_system_mixing` (Node.js) — CJS↔ESM is architectural
- `console_log_in_service` (Node.js) — logger choice is project-specific
- `console_writeline_in_service` (C#) — logger choice is project-specific
- `missing_async_await` (C#) — removing `async` may break interfaces
- `invalid_java_version` (Java) — version is architectural
- `interface_file_contains_class` (Java/C#) — requires file split

**Deferred repairable (feasible, not yet built):**
- `unhandled_promise` (Node.js) — try/catch wrapping is mechanical
- `missing_override` (Java) — @Override insertion is deterministic
- `raw_type_usage` (Java) — generic parameterization is mostly deterministic
- `namespace_filepath_mismatch` (C#) — namespace rewrite is deterministic
- `missing_nullable_in_csproj` (C#) — XML edit is trivial

---

## Insight 5: The Kaizen Feedback Loop Has a Missing First Mile

### What the requirements assume

KAIZEN_PRIME_REQUIREMENTS.md Layer 5 (REQ-KZ-500-504) specifies the feedback loop as:

```
Post-mortem detects pattern → Generate suggestion → Write kaizen-config.json →
Inject hint into next run's prompt → Verify improvement
```

This is the **last mile** of the feedback loop — getting detected patterns into the next prompt. It's well-specified and well-implemented.

### What planning revealed

The **first mile** is missing: getting language-specific quality guidance into the CURRENT run's prompt. The requirements focus entirely on cross-run improvement (run N's failures improve run N+1's prompts) but never specify that run N should benefit from the language profile's built-in quality guidance.

Every `LanguageProfile` already has `coding_standards` — rich, idiomatic guidance that would prevent the very defects the Kaizen system later detects:

- Node.js `coding_standards` says "Use `const` instead of `var`" — prevents `var_usage` defect
- Go `coding_standards` says "Always check returned errors" — prevents `unchecked_error` defect
- C# `coding_standards` says "Use file-scoped namespaces" — prevents `block_scoped_namespace` defect

But no requirement says "inject `coding_standards` into the spec/draft prompt." The LLM generates code blind to the language's idioms, the Kaizen system detects the resulting defects, generates suggestions, and injects them into the NEXT run. The first run always pays the full defect cost.

### Proposed amendment

**Add to KAIZEN_PRIME_REQUIREMENTS.md Layer 5:**

> **REQ-KZ-505: First-Run Quality Injection (Language Standards)**
>
> The Prime Contractor SHALL inject `language_profile.coding_standards` into the spec prompt for every run, regardless of whether Kaizen config exists. This provides baseline quality guidance that does not depend on prior run history.
>
> **Rationale:** The Kaizen feedback loop (REQ-KZ-500-504) requires at least one failed run to generate suggestions. `coding_standards` injection provides prevention-based quality for the first run, complementing the detection-based quality of the Kaizen loop.
>
> **Interaction with REQ-KZ-502:** If a Kaizen config also contains `prompt_hints` for the same issue (e.g., both `coding_standards` and a Kaizen hint say "use `const` not `var`"), deduplicate by content hash. `coding_standards` are injected as a P0 section (never truncated by `enforce_prompt_budget()`). Kaizen hints are injected as P1 (truncatable).
>
> **Prompt budget:** `coding_standards` content is typically 200-500 tokens per language. This is within the `TOTAL_SPEC_BUDGET_TOKENS` (4096) limit. If a language profile's `coding_standards` exceeds 1000 tokens, truncate to the first 1000 with a `[truncated]` marker.

**Add to MULTI_LANGUAGE_PARITY_REQUIREMENTS.md Section 4:**

> **REQ-MLP-PROMPT-CTX:** `spec_builder.py` SHALL extract `language_profile.coding_standards` and inject it as a "## Coding Standards" section in every spec prompt. This is NOT a Kaizen feature — it is a baseline generation quality feature that applies to every run.

---

## Insight 6: The Parity Matrix Grades Components, Not Pipelines

### What the requirements assume

MULTI_LANGUAGE_PARITY_REQUIREMENTS.md Section 2 grades each language on 5 dimensions: Syntax Validation, Repair Pipeline, Semantic Validation, Disk Compliance, Post-Generation. Each dimension is graded independently.

### What planning revealed

The grades are misleading because they measure component existence, not pipeline connectivity. Consider Java:

| Dimension | Grade | Reality |
|-----------|-------|---------|
| Semantic Validation | "12 checks" → A | 12 checks exist, all fire, all collect... but 6 have no repair route and produce advisory-only output |
| Kaizen Suggestions | "All mapped" → A | All mapped — this is genuinely complete |
| Repair Pipeline | "4/10 routes" → C | Only 4 of 12 semantic checks can actually be repaired |

The Semantic Validation grade of A and the Repair Pipeline grade of C make it look like two independent problems. But they're the same problem: **the semantic→repair pipeline is 33% connected.** The detection end is complete; the action end is not.

### Proposed amendment

**Replace the component-based parity matrix with a pipeline-based matrix** that traces each semantic check from detection through to action:

| Check | Detected? | Collected? | Scored? | Suggestion? | Repair? | End-to-End? |
|-------|:-:|:-:|:-:|:-:|:-:|:-:|
| `check_empty_catch_blocks` (Java) | Y | Y | Y | Y | N (advisory) | ADVISORY |
| `check_raw_type_usage` (Java) | Y | Y | Y | Y | N (deferred) | **BROKEN** |
| `check_module_system_consistency` (Node.js) | Y | Y | Y | Y | N (advisory) | ADVISORY |
| `check_duplicate_main_guards` (Python) | Y | **N** | **N** | **N** | Y | **BROKEN** |

A check graded "BROKEN" has partial wiring — it detects but doesn't complete the pipeline. A check graded "ADVISORY" intentionally stops at detection + suggestion. Only checks graded "COMPLETE" or "ADVISORY" are considered fully wired.

**New metric:** Pipeline Connectivity Rate = (COMPLETE + ADVISORY) / Total checks

| Language | Checks | Complete | Advisory | Broken | Connectivity |
|----------|:------:|:--------:|:--------:|:------:|:-----------:|
| Python | 4 | 0 | 0 | 4 | **0%** |
| Go | 6 | 5 | 0 | 1 | **83%** |
| Node.js | 9 | 3 | 3 | 3 | **67%** |
| Java | 12 | 4 | 2 | 6 | **50%** |
| C# | 9 | 4 | 2 | 3 | **67%** |

This metric is more actionable than the current per-dimension grades because it reveals exactly where the disconnections are.

---

## Insight 7: Quick Wins That Were Invisible Before Planning

The planning process exposed quick wins that weren't visible from the requirements alone. These are situations where the requirements specify a complex solution but a simpler one exists, or where the requirements miss a trivial fix that has disproportionate impact.

### QW-A: `coding_standards` injection is simpler than Kaizen hint wiring

**What the requirements specify:** A multi-run feedback loop (REQ-KZ-500-504) where run N's failures generate suggestions that improve run N+1's prompts. This is 5 requirements across 2 systems (SDK + cap-dev-pipe).

**What planning revealed:** A single-line extraction (`gen_context["coding_standards"] = self._language_profile.coding_standards`) provides 80% of the same defect prevention for run 1, with zero cross-run infrastructure. The full Kaizen loop is still valuable for run-specific learning, but the first-run quality floor comes from a trivial wiring fix, not a multi-layer system.

**Impact:** Every run of every language benefits immediately. This is not a replacement for Kaizen — it's a complement that makes Kaizen's job easier (fewer defects to detect means fewer suggestions to generate means cleaner trend data).

### QW-B: The 4 Python suggestion mappings are a 10-minute fix with outsized impact

**What the requirements assume:** Python's feedback loop works because Python is the primary language.

**What planning revealed:** Python has ZERO Kaizen suggestion mappings. Every Python semantic check fires silently into a void. Adding 4 dictionary entries takes 10 minutes and immediately activates the entire Kaizen feedback loop for Python — the language with the most runs and the most data.

### QW-C: `.ts/.tsx/.jsx` extension dispatch is a 1-line fix

**What the requirements specify:** KAIZEN_NODEJS_REQUIREMENTS.md defines 11 semantic checks covering both JavaScript and TypeScript.

**What planning revealed:** The dispatch only routes `.js/.mjs/.cjs` to validation. TypeScript files — arguably the more important target in modern Node.js — are silently skipped. One additional tuple element in the suffix check enables all existing semantic checks for TypeScript with zero new code.

### QW-D: The `self.` false positive corrupts ALL Node.js Kaizen metrics

**What the requirements specify:** KAIZEN_NODEJS_REQUIREMENTS.md QW-1 identifies this bug and estimates 5 minutes to fix.

**What planning revealed:** This is worse than a single false positive. When `_check_python_contamination()` triggers on `"help yourself."`, it emits a CRITICAL severity issue that sets the file's quality score to 0.0. This 0.0 score:
1. Drags down the run's `aggregate_score`
2. Generates a `CROSS_LANGUAGE_CONTAMINATION` root cause
3. Produces a Kaizen suggestion to "generate JavaScript, not Python"
4. Corrupts the Kaizen trend data (success rate appears lower than reality)
5. May trigger a Kaizen config injection that adds unnecessary "write JavaScript" hints

One false positive propagates through 5 pipeline stages, each amplifying the error. The fix is regex anchoring; the impact is data integrity across all downstream Kaizen analysis.

### QW-E: `_REPAIRABLE_CATEGORIES` documentation prevents future wiring gaps

**What the requirements don't specify:** Why certain checks lack repair routes.

**What planning revealed:** Adding a comment block to `semantic_bridge.py` that classifies each category as REPAIRABLE/ADVISORY/DEFERRED with a one-line reason takes 15 minutes and permanently prevents the "is this a bug or a design choice?" confusion that consumed audit time across all 5 languages.

### QW-F: The `validate_disk_compliance()` call in integration engine is reusable

**What the requirements specify for P1-1:** Wire Python semantic checks into the integration engine using `validate_disk_compliance()`.

**What planning revealed:** If we call `validate_disk_compliance()` for Python files in `_run_semantic_checks()`, we could also call it for ALL languages — it already dispatches to `_validate_non_python_file()` internally. This would eliminate the per-language dispatch branches in `_run_semantic_checks()` entirely, replacing ~200 lines of if/elif with a single `validate_disk_compliance()` call per file.

However, this is a bigger refactor than the targeted fix. The risk is that `validate_disk_compliance()` is more expensive per file than the targeted semantic checks (it runs 10 layers for Python). The quick win is the targeted fix; the architectural improvement is the unified call.

---

## Summary: Requirements Amendments Needed

| # | Amendment | Target Document | Section | Type |
|---|-----------|----------------|---------|------|
| A1 | Add "Layer 0 — Language Backbone Contract" | KAIZEN_PRIME_REQUIREMENTS.md | New section before Layer 1 | NEW REQUIREMENT |
| A2 | Add baseline verification for Python reference impl | MULTI_LANGUAGE_PARITY_REQUIREMENTS.md | Section 1 | AMENDMENT |
| A3 | Add REQ-KZ-510 Semantic Check Pipeline Completeness Invariant | KAIZEN_PRIME_REQUIREMENTS.md | Layer 5 | NEW REQUIREMENT |
| A4 | Add advisory/repairable/deferred classification to all checks | MULTI_LANGUAGE_PARITY_REQUIREMENTS.md | Section 4.2 | AMENDMENT |
| A5 | Add REQ-KZ-505 First-Run Quality Injection | KAIZEN_PRIME_REQUIREMENTS.md | Layer 5 | NEW REQUIREMENT |
| A6 | Replace component grades with pipeline connectivity matrix | MULTI_LANGUAGE_PARITY_REQUIREMENTS.md | Section 2 | AMENDMENT |
| A7 | Add 5-column implementation checklist template for new checks | All language-specific requirements docs | Verification sections | AMENDMENT |

## Quick Win Summary

| # | Fix | Effort | Impact | Prevents |
|---|-----|--------|--------|----------|
| QW-A | `coding_standards` → `gen_context` | ~20 min | ALL languages, run 1 | Defects the Kaizen system later detects |
| QW-B | 4 Python `_SEMANTIC_CATEGORY_TO_SUGGESTION` entries | ~10 min | Python Kaizen loop | Silent suggestion drops |
| QW-C | `.ts/.tsx/.jsx` in suffix dispatch | ~1 min | All TypeScript projects | Silent validation skips |
| QW-D | `self.` regex anchoring | ~5 min | All Node.js Kaizen data | 5-stage error propagation |
| QW-E | `_REPAIRABLE_CATEGORIES` classification comments | ~15 min | Future languages | Repeat wiring confusion |
| QW-F | Unified `validate_disk_compliance()` dispatch | ~2 hrs | Architecture simplification | Per-language dispatch maintenance |
