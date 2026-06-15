# Primary Contractor Cleanup (FR-10) — Implementation Plan

**For:** `PRIMARY_CONTRACTOR_CLEANUP_REQUIREMENTS.md`
**Date:** 2026-05-31
**Target:** `src/startd8/workflows/builtin/primary_contractor_workflow.py` (+ its tests)
**Branch:** dedicated branch in the `~/Documents/dev/startd8-phase5` worktree (independent of Phase 5).

---

## Planning discoveries (feed the requirements §0)

| v0.1 assumption | Planning revealed | Impact |
|-----------------|-------------------|--------|
| ~10 re-exports are "src-internal, keep/rewire" | **Zero** are src-internal. The raw name-grep hits were **same-named symbols defined elsewhere** (`implementation_engine/budget.py`, `spec_builder.py`, `artisan_phases/development.py`'s own `_build_output_format`). The workflow uses **none** of its re-exports internally (`internal_uses=0` for all 14). | FR-1+FR-2 collapse: the **entire** re-export block is removable — 4 unused + 10 test-only, **no src rewiring**. |
| FR-2 migrates whole test import lines | Tests import a **mix** of re-exports *and* genuinely workflow-own private fns (`_format_lead_prompt`, `_build_multi_file_directive`, `_build_output_format`) in the same multi-line blocks. | Migration is **per-symbol**, not per-line. Workflow-own privates stay. |
| Re-exports might be mock-patch targets (OQ-5) | **None** patch `primary_contractor_workflow._X`. | Plain import swap — zero behavior risk. |
| Config dup at "old 433-787 vs 1025-1318" | Actual dup is the **8-key block** at sync `365-377` vs async `1042-1053`, byte-identical. | FR-3 scope is small + precise. |

**Resolved:** OQ-1 (4 confirmed unused), OQ-2 (no src/downstream re-export consumers), OQ-3 (dup confirmed, exact lines), OQ-5 (no patches). **Open:** OQ-4 (return type — see Step 3), OQ-6 (one PR — yes).

---

## Step 1 — FR-1: delete the 4 unused re-exports
- **File:** `primary_contractor_workflow.py` lines in 132-147.
- Delete: `_SPEC_CONTEXT_BUDGET_CHARS`, `_SEARCH_REPLACE_LINE_THRESHOLD`, `_truncate_with_marker`, `_truncate_arch_context` (confirmed 0 internal + 0 real importers; the `src` name-hits are unrelated same-named symbols).
- **Verify:** `git grep -nw <name>` shows only unrelated defs; full suite green.

## Step 2 — FR-2: migrate test-only re-exports, then delete them
- **Mapping** (re-export → real source for the test import):
  - `_PLAN_CONTEXT_MAX_CHARS`, `_ARCH_CONTEXT_MAX_CHARS`, `_EXISTING_FILES_BUDGET_BYTES`, `_TRUNCATION_MARKER` → `startd8.implementation_engine.budget` (names without leading `_`, e.g. `PLAN_CONTEXT_MAX_CHARS`).
  - `_get_drafter_system_prompt` → `implementation_engine.drafter.get_drafter_system_prompt`; `_build_existing_files_section` → `drafter.build_existing_files_section`; `_build_output_format` → `drafter.build_output_format`.
  - `_PLAN_CONTEXT_EDIT_FRAMING_FALLBACK`, `_PLAN_CONTEXT_CREATE_FRAMING_FALLBACK`, `_ARCH_CONTEXT_EDIT_FRAMING_FALLBACK` → `implementation_engine.spec_builder` (private names; import as-is).
- **Importing test files** (per-symbol edits only): `tests/unit/test_primary_contractor_workflow.py`, `tests/unit/workflows/conftest.py`, `tests/unit/workflows/test_prime_prompt_externalization.py`, `tests/unit/test_prime_task_enrichment.py`, `tests/unit/contractors/test_multi_file_edit_fixes.py`, `tests/test_edit_mode_regression.py`. In multi-symbol import blocks, **move only the re-export symbols** to a new import from the source module; **leave** workflow-own privates (`_format_lead_prompt`, `_build_multi_file_directive`, etc.) importing from `primary_contractor_workflow`.
- After all importers are migrated, **delete the remaining `_X = _ie_*` re-export lines** + the `# Backward-compatible re-exports for existing tests…` comment.
- **Verify:** `grep -nE "^_[A-Za-z_]+ = _ie" primary_contractor_workflow.py` empty; suite green with **assertions unchanged** (only import lines differ).

## Step 3 — FR-3: extract `_parse_primary_config`
- Add a module-private helper returning a small **NamedTuple** (`_PrimaryRunConfig`) with the 8 fields (`lead_spec, drafter_spec, max_iterations, pass_threshold, output_format, integration_instructions, check_truncation, legacy_fail_on_truncation`) — NamedTuple chosen over dict: typed, immutable, call sites change from `x = config.get(...)` to `cfg = self._parse_primary_config(config); ... cfg.x` with minimal churn and no behavior change. *(Resolves OQ-4.)*
- Replace the byte-identical blocks at **sync `365-377`** and **async `1042-1053`** with a call to the helper.
- **Care:** preserve the exact `fail_on_truncation` legacy-flag semantics (the `legacy_fail_on_truncation` handling that follows) — keep that logic identical; only the `config.get` extraction is shared.
- **Verify:** identical resolved values for identical input config (a small unit test may assert the parser, but no existing assertion changes); suite green.

## Step 4 — Verify behavior parity (FR-4, the gate)
- `pytest -p no:cacheprovider -m "not integration"` on the affected suites + a broad run; compare to the pre-change green baseline.
- `git diff` on test files = **import-line changes only** (no assertion edits).
- Integration tests stay skipped (opt-in).

## Sequencing / PR (OQ-6)
One PR is fine — all steps are behavior-preserving and verified by the same unchanged test suite. Internal commit order: Step 1 → Step 3 (src-only) → Step 2 (test migration last, so the src removals are validated before touching tests). Independent of Phase 5; can land anytime.
