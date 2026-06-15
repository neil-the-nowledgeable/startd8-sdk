# Primary Contractor Workflow — Accidental-Complexity Cleanup (FR-10) Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-05-31
**Status:** Planned — ready to implement
**Origin:** Deferred follow-up to the lead-contractor removal effort (R2-F4 → R3-F6, triaged ACCEPT).
See `LEAD_CONTRACTOR_REMOVAL_REQUIREMENTS.md` Appendix A (R3-F6) and Appendix B (R3-F4 rejected).
**Component:** `src/startd8/workflows/builtin/primary_contractor_workflow.py` (+ its tests).
**Plan:** `PRIMARY_CONTRACTOR_CLEANUP_PLAN.md`.

---

## 0. Planning Insights (Self-Reflective Update)

> What the planning pass (reading the real code) revealed vs. the v0.1 draft.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| ~10 re-exports are "src-internal — keep/rewire" | **Zero** are src-internal. The raw name-grep hits were **same-named symbols defined in other modules** (`implementation_engine/budget.py`, `spec_builder.py`, and `artisan_phases/development.py`'s own `_build_output_format` method). The workflow uses **none** of its 14 re-exports internally. | FR-1 + FR-2 collapse into "remove the whole block": 4 unused + 10 test-only, **no src rewiring**. Lower risk, smaller scope. |
| FR-2 migrates whole test import lines | Tests import a **mix** of re-exports *and* genuinely workflow-own private fns (`_format_lead_prompt`, `_build_multi_file_directive`) in the same multi-line `import (...)` blocks. | Migration is **per-symbol**: move only the re-exports to the source module; leave workflow-own privates importing from the workflow. |
| Re-exports might be mock-patch targets | **No** test patches `primary_contractor_workflow._X`. | Plain import swap — no behavior-sensitive patch repointing. |
| Config-parse dup at "old 433-787 vs 1025-1318" | Actual dup is the **8-key `config.get` block** at sync `365-377` vs async `1042-1053`, byte-identical. | FR-3 scope is small and precise. |

**Resolved open questions:**
- **OQ-1 → Yes, the 4 are truly unused** (`_SPEC_CONTEXT_BUDGET_CHARS`, `_SEARCH_REPLACE_LINE_THRESHOLD`, `_truncate_with_marker`, `_truncate_arch_context`) — 0 internal uses, 0 real importers.
- **OQ-2 → No src/ or downstream consumer imports any re-export**; the apparent src hits were unrelated same-named symbols. FR-2 is pure test migration.
- **OQ-3 → Dup confirmed** at sync `365-377` / async `1042-1053`.
- **OQ-4 → `_parse_primary_config` returns a NamedTuple** (`_PrimaryRunConfig`) — typed, immutable, minimal call-site churn.
- **OQ-5 → No mock-patch targets** on the re-exports.
- **OQ-6 → One PR**, internal-only, behavior-preserving; independent of Phase 5.

---

## 1. Problem Statement

The lead→primary rename left adjacent accidental complexity in
`primary_contractor_workflow.py` that the rename PRs deliberately did **not** touch:

| Component | Current State | Gap |
|-----------|--------------|-----|
| Back-compat re-export block (`primary_contractor_workflow.py:132-147`, 14 `_X = _ie_*.Y` lines) | Re-exports budget/drafter/spec_builder internals under module-private names purely "for existing tests." Used by no `src/` code and not by the workflow itself. | A module re-exporting another module's internals as a test-import facade — pure clutter. |
| Config parsing in sync + async execute paths | The 8-key `config.get(...)` block is **byte-duplicated** (sync `365-377`, async `1042-1053`). | Two copies drift independently; a new config key can be added to one and missed in the other. |

Goal: reduce this complexity **without changing behavior** — same inputs → same generated code,
costs, and review outcomes, verified by the existing suite passing with **unchanged assertions**.

## 2. Requirements

- **FR-1 Delete the unused re-exports.** Remove the four re-export lines referenced nowhere:
  `_SPEC_CONTEXT_BUDGET_CHARS`, `_SEARCH_REPLACE_LINE_THRESHOLD`, `_truncate_with_marker`,
  `_truncate_arch_context`. *Acceptance:* names absent from the module; suite green unchanged.

- **FR-2 Remove the test-only re-exports by migrating their (test) importers to the source module.**
  The other 10 re-exports are imported **only by tests**. Per-symbol, update those test imports to
  pull the symbol directly from its real home (`startd8.implementation_engine.{budget,drafter,spec_builder}`),
  leaving workflow-own private functions (`_format_lead_prompt`, `_build_multi_file_directive`, …)
  importing from `primary_contractor_workflow`. Then delete the now-unused `_X = _ie_*` lines and the
  "Backward-compatible re-exports…" comment. *Acceptance:* `grep -nE "^_[A-Za-z_]+ = _ie"` on the
  module is empty; migrated tests pass with **import-line-only** diffs (no assertion changes).

- **FR-3 Extract one shared config parser.** Add `_parse_primary_config(config) -> _PrimaryRunConfig`
  (NamedTuple, 8 fields) consumed by both the sync and async paths, replacing the duplicated
  `config.get` blocks. The downstream `legacy_fail_on_truncation` semantics are preserved exactly;
  only the extraction is shared. *Acceptance:* both paths call the helper; the duplicated literal
  blocks are gone; identical resolved values for identical input; suite green unchanged.

- **FR-4 Behavior parity is the gate.** No assertion is weakened, skipped, or `xfail`-ed. Test edits
  are **import-line-only**. *Acceptance:* `git diff` on tests shows import-only edits; non-test
  behavior assertions byte-identical; `pytest -m "not integration"` matches the pre-change baseline.

## 3. Non-Requirements

- Does **not** perform the full sync/async execution-path merge beyond config parsing (deferred).
- Does **not** change any public API, behavior, prompt semantics, cost, or review logic.
- Does **not** touch downstream consumer repos.
- Does **not** rename `lead_agent`/`drafter_agent` config keys (R3-F4 rejected — role names).
- Does **not** depend on or block the Phase-5 breaking removal — independent, non-breaking.

## 4. Open Questions

*All resolved during planning — see §0 (OQ-1…OQ-6).*

---

*v0.2 — Post-planning self-reflective update. 2 requirements simplified (the false "src-internal"
split collapsed; FR-2 made per-symbol), FR-3 scoped to exact lines, 6 open questions resolved.
0 requirements deferred beyond the original full-merge non-goal.*
