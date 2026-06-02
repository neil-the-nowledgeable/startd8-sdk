# Run-012 Failure Investigation — What Files I'm Looking For, and Why

**Date:** 2026-06-01
**Run:** `run-012-20260601T1838`
**Source artifacts (read):**
- `…/run-012-20260601T1838/plan-ingestion/prime-postmortem-summary.md` (0.67 / FAIL)
- `…/run-012-20260601T1838/plan-ingestion/prime-postmortem-report.json` (per-feature
  `disk_compliance.semantic_issues`)
**Purpose:** ground the *repair-retry* requirements (`REPAIR_RETRY_REQUIREMENTS.md`) in the
exact on-disk reality of the latest failure, and record the file-existence searches that
determine each violation's repair class.

---

## 1. The question this investigation answers

Run-012 failed 5 of 15 features, **all** with `unresolvable_import` cross-file contract
violations. For a *repair* (no LLM regeneration) to fix an unresolvable import, the import
must point at the **wrong path for a file that exists** (rewritable). If instead the target
file **doesn't exist anywhere**, there is nothing to rewrite to — the fix is to *create* the
target (scaffold) or to *regenerate* the missing feature.

So the load-bearing question per violation is binary:

> **Does the import's target file exist somewhere on disk (run output or project)?**

That is the only thing I was searching the filesystem for. I was **not** looking for any
additional report files — the two postmortem artifacts above are complete.

---

## 2. The 5 import targets searched (the files I'm looking for)

Run-root = `…/run-012-20260601T1838/plan-ingestion/generated/`. Each importing `.tsx` exists;
the question is whether its import target exists.

| # | Feature | Importing file (exists ✅) | Import specifier | Target file searched | Found? |
|---|---------|----------------------------|------------------|----------------------|:------:|
| 1 | PI-007 | `components/wizard/StepNav.tsx` | `./StepNav.module.css` | `components/wizard/StepNav.module.css` | ❌ |
| 2 | PI-005 | `components/wizard/ModeToggle.tsx` | `./ModeToggle.module.css` | `components/wizard/ModeToggle.module.css` | ❌ |
| 3 | PI-011 | `components/wizard/steps/ProofPointStep.tsx` | `./ProofPointStep.module.css` | `components/wizard/steps/ProofPointStep.module.css` | ❌ |
| 4 | PI-012 | `components/wizard/steps/EnrichStep.tsx` | `../../../types/wizard` | the shared-types module | ✅ as `components/wizard/types.ts` (see §4) |
| 5 | PI-008 | `components/wizard/WizardShell.tsx` | `@/components/wizard/steps` | `components/wizard/steps/index.{ts,tsx}` (barrel) | ❌ |

**Search scope:** the entire run directory (`…/run-012-20260601T1838/`, not just `generated/`)
**and** the target project tree (`…/strtd8/strtd8`, excluding `node_modules`). All five targets
were absent in both.

\* **#4 has a caveat (see §4).**

---

## 3. Repair-class determination

Because the targets are *missing*, not *misnamed*, these violations fall outside the
path-rewrite lever (the just-merged name-repair `import_path_rename` step would correctly
**abstain** — there is no on-disk path to rewrite to). They split into:

| Class | Violations | Deterministic fix (no LLM) |
|-------|-----------|----------------------------|
| **rewritable-path** | #4 (`../../../types/wizard`) | The real module **exists** at `components/wizard/types.ts` (PI-006, success). Rewrite the import to `@/components/wizard/types` (or `../types`). See §4. |
| **missing-cofile / scaffoldable** | #1, #2, #3 (`*.module.css`) | Create an empty `*.module.css` co-file so the import resolves and the component compiles (styling filled later). |
| **missing-barrel / scaffoldable** | #5 (`@/components/wizard/steps`) | Generate a barrel `steps/index.ts` re-exporting the sibling step components that already exist in `steps/`. |

Net: **1 of 5** is a path-rewrite (#4); **4 of 5** are *scaffold-the-missing-target* (#1-3, #5).
**0 of 5** need regeneration — every run-012 failure is deterministically repairable without an
LLM, given a rewrite lever + a scaffold lever.

---

## 4. Case #4 resolved — REWRITABLE

The `Wizard shared types` feature is **PI-006**, and it **succeeded**: its `target_files` is
`['components/wizard/types.ts']` and its `generated_files` confirms it wrote
`…/generated/components/wizard/types.ts` (verified on disk).

So `EnrichStep.tsx` (at `components/wizard/steps/`) importing `../../../types/wizard` is a
**wrong path**, not a missing file. The real module is co-located at `components/wizard/types.ts`:

- from `components/wizard/steps/` the correct relative specifier is **`../types`**
  (`steps/` → `wizard/`, then `types`), or the alias form **`@/components/wizard/types`**.
- `../../../types/wizard` climbs three levels (to the run root) into a non-existent
  `types/wizard` — the classic invented-canonical-path failure (RUN-011 family).

**Class = rewritable-path.** This is precisely the lever the name-repair `import_path_rename`
step targets — *but only if its resolver is broadened beyond `@/lib/*`* to the project's full
resolvable surface (here `components/wizard/types.ts`). That broadening is a named requirement
(see `REPAIR_RETRY_REQUIREMENTS.md` FR-4 / the name-repair `TruthSource`).

---

## 5. Why this matters for the requirements

This investigation is the empirical basis for `REPAIR_RETRY_REQUIREMENTS.md`:

1. Repair-retry's dominant lever for *this* run is **scaffold the missing resolvable target**
   (empty CSS module ×3, barrel index ×1) — a repair class the name-repair pipeline does **not**
   have. So the requirements must add a scaffold lever, not just re-run name-repair.
2. The one rewritable case (#4) needs the name-repair **resolver broadened beyond `@/lib/*`** to
   the project's full resolvable surface — otherwise even the rewritable case abstains.
3. Repair-retry needs a **violation classifier** (rewritable-path | scaffoldable | needs-regen)
   that performs exactly the target-existence search recorded above.
4. The needs-regen residue (none in run-012, but a general case) must surface as a **precise
   targeted-regen worklist** (`feature_id` + missing target), not a silent failure.

**Headline:** with both levers (rewrite + scaffold), **all 5 of run-012's failures are
deterministically repairable with zero LLM calls** — a 0.67/FAIL run could become a PASS on a
pure repair-retry pass.

---

*Companion to `REPAIR_RETRY_REQUIREMENTS.md` and `REPAIR_RETRY_PLAN.md`. The file-existence
searches in §2 are reproducible via `find` over the run dir + project tree.*
