# Convergent Review Protocol (CRP) — Recursive Decomposition Core Guide

**Purpose:** Apply the CRP to the recursive decomposition requirements and implementation plan for Micro Prime.

**Protocol source:** `docs/design/arc-review/ARCHITECTURAL_REVIEW_REQUIREMENTS.md`

---

## Scope

This guide applies to two documents only:

1. `docs/design/decomposer/REQ-MP-910_RECURSIVE_DECOMPOSITION_CORE.md`
2. `docs/design/decomposer/RECURSIVE_DECOMPOSITION_CORE_IMPLEMENTATION_PLAN.md`

Run CRP separately for each document. Each document keeps its own appendix and round numbering.

---

## Suggestion ID Formats

- Requirements doc: `R{round}-F{n}`
- Implementation plan: `R{round}-S{n}`

---

## First-Encounter Initialization

If the target document does not contain this heading:

```
## Appendix: Iterative Review Log (Applied / Rejected Suggestions)
```

append the standard CRP appendix template to the end of that document without modifying the body.

Use the exact template from `docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md`.

---

## Review Areas

Use the standard 7 CRP areas. Focus emphasis for this scope:

- Architecture: decomposition core module boundaries and integration points
- Interfaces: context objects, plan graphs, strategy registry compatibility
- Data: plan graph structure, recursion path tracking, rejection reason boundedness
- Risks: recursion bounds, cycle detection, partial writes, cache staging
- Validation: AST checks, rollback behavior, monotonicity enforcement
- Ops: metrics, logging, postmortem metadata
- Security: avoid unsafe execution during validation (static analysis only)

---

## Document-Specific Guidance

### REQ-MP-910_RECURSIVE_DECOMPOSITION_CORE.md

- Verify that recursion policy defaults preserve current behavior.
- Ensure rejection reasons are bounded and consistent with existing metrics conventions.
- Confirm that Decomposition Core types do not break REQ-MP-9xx compatibility.
- Check that observability is enabled only when recursion is enabled.

### RECURSIVE_DECOMPOSITION_CORE_IMPLEMENTATION_PLAN.md

- Verify each requirement has a concrete change and test.
- Confirm staging and rollback are explicitly covered.
- Ensure config wiring is described before execution changes.
- Ensure recursion metrics and metadata are added only after policy and execution are defined.

---

## Workflow

1. Parse Appendix A, B, C if present.
2. Determine round number for the specific document.
3. Compute coverage by area using accepted suggestions in Appendix A.
4. Run two-tier review if any area is below threshold.
5. Append a new review round to Appendix C.
6. Do not modify any prior rounds.

---

## Appendix Template (Required)

If missing, append the standard CRP appendix verbatim from `docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md`.
