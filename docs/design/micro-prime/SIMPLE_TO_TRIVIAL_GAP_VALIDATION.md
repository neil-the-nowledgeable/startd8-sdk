# Simple → Trivial Decomposer — Gap Report Validation

**Date:** 2026-03-07
**Scope:** Phase 0 gaps reported by Codex implementation-readiness audit
**Source plan:** [SIMPLE_TO_TRIVIAL_DECOMPOSER_IMPLEMENTATION_PLAN.md](./SIMPLE_TO_TRIVIAL_DECOMPOSER_IMPLEMENTATION_PLAN.md)

---

## Summary

Three items were flagged as missing from the implementation plan. All three are **false positives** — each is already specified in the plan body.

---

## Findings

### 1. OTel metrics (`prime.file_copy_tasks`, `prime.file_copy_cost_saved_usd`)

| Field | Value |
|-------|-------|
| **Reported status** | Missing — "Not instrumented" |
| **Actual status** | Present |
| **Plan location** | Phase 0, Step 5 (line 52) |
| **Exact text** | `prime.file_copy_tasks`, `prime.file_copy_cost_saved_usd` OTel counters |
| **Verdict** | False positive |

### 2. `copy_and_modify` prompt injection (`{reference_implementation}` slot)

| Field | Value |
|-------|-------|
| **Reported status** | Missing — "Detection returns None for modified copies but no prompt injection path" |
| **Actual status** | Present |
| **Plan location** | Phase 0, Step 4 (line 50) |
| **Exact text** | "inject predecessor output as `{reference_implementation}` in the spec prompt. Still uses LLM but with better context. **Dependency:** Prompt templates used in the spec/draft phase must accept an optional `{reference_implementation}` slot. If the slot is absent from the template, the predecessor output is silently omitted (no crash). Render test required to verify injection." |
| **Verdict** | False positive |

### 3. Prompt-budget guard for reference injection (2000 token budget)

| Field | Value |
|-------|-------|
| **Reported status** | Missing — "N/A since copy_and_modify not implemented" |
| **Actual status** | Present |
| **Plan location** | Phase 0, Step 4 (line 50, second half of paragraph) |
| **Exact text** | "**Prompt-budget guard** (R4-S6, Leg 10 #37): before injecting `{reference_implementation}`, measure its token count against a configurable budget (default: 2000 tokens). If the predecessor output exceeds the budget, apply tiered compression: (1) strip comments and docstrings, (2) truncate to budget with a `# [TRUNCATED — full source: {path}]` marker." |
| **Verdict** | False positive |

---

## Root Cause

The gap reporter likely operated on a stale snapshot of the plan (pre-R4 triage) or failed to parse Phase 0 Step 4, which packs two concerns — `copy_and_modify` injection and prompt-budget guard — into a single paragraph. Items 2 and 3 were added during the R4-S6 triage pass on 2026-03-07.

---

## Recommendation

No plan changes required. Future gap audits should:

1. **Re-read the plan** immediately before reporting — the plan is iteratively refined and earlier reads go stale.
2. **Search by keyword** (`file_copy`, `reference_implementation`, `budget`) rather than scanning by step number, since steps can be restructured across triage rounds.
3. **Check Appendix A** for applied suggestion IDs — if a suggestion is listed as applied, the corresponding plan body change exists.
