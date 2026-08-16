# Reconcile local `main` ↔ `origin/main` — Plan

**Date:** 2026-08-16 · **Owner:** neil · **Strategy (chosen):** unify locally first, publish later
**Safety bar:** 100% non-destructive — every step is isolated or read-only until one final, reviewed publish.

## Goal

Bring local `main` and `origin/main` back onto one history **without losing either side's work**. Step 1
(this plan) makes **local `main` whole**: it gains origin's non-navigator work (coverage-map, RULE_CATALOG,
`startd8 validate`, SARIF, collector-enrichment, CI) while keeping local's 139 commits. Publishing the
unified result to `origin` is a **separate, later** decision (see §7) — deliberately out of scope here so
we take zero origin risk now.

## Diagnosis (as of pin `bf8b5b58`, origin `7d2e4e18`)

- **Diverged** at merge-base `8c53fc54` (PR #464, Aug-14) — a ~2-day fork.
- **27 commits behind** (origin-only) · **139 ahead** (local-only). NOT fast-forwardable — a true fork.
- **105 files overlap, but only 12 actually conflict.** The other 93 (incl. ALL origin non-nav work)
  auto-merge — that clean set is the prize: local gains coverage-map / rule-catalog / validate / CI.
- The 12 conflicts are entirely the **navigator/viz subsystem**, which exists on both sides: origin as the
  #476 squash-snapshot + #479 cherry-scope; local as the full evolved history. **Local is the newer
  superset** in every case.

## The knots (12 files)

### KNOT 1 — 3 code files (real 3-way reads; resolve **local-wins**, but verify each)

| File | Δlines | local / origin | Divergence | Resolution |
|------|--------|----------------|------------|------------|
| `src/startd8/navigator/cli_navigator.py` | 223 | 743 / 530 | local has `--source pipeline` + `verify` + REQ-15 frame; origin snapshot lacks them | take **local**; confirm origin #479's frame branch isn't newer |
| `src/startd8/navigator/provenance.py` | 144 | 186 / 48 | local has `pipeline_provenance` + FR-id + HTML; origin has the 48-line stub | take **local** (clear superset) |
| `src/startd8/navigator/view_definition.py` | 40 | 561 / 523 | local has `PIPELINE_DEFINITION`; origin's #479 deliberately removed it | take **local**; re-confirm REQ-14/15 bodies match |

### KNOT 2 — moving target (the hardest part, not the code)

Local `main` advanced **twice during diagnosis** (`79a03449 → bf8b5b58`) and origin got #480 — both trees
move every few minutes under concurrent agents. Mitigation baked into the procedure: **pin a SHA, merge in
an isolated worktree, and re-verify the primary tip before any publish.** Because we MERGE (not rebase),
the 139 local SHAs are **preserved** — no in-flight branch/worktree is invalidated (see §6).

### KNOT 3 — publishing carries other agents' work (DEFERRED)

The 139 local commits are largely other agents' (node-ir REQ-16/17, REQ-08 v0.4). Any origin publish carries
them. Out of scope for step 1; §7 gates it behind their awareness.

### 9 doc conflicts (quick — resolve **local-wins**, spot-verify superset)

`ENHANCEMENT_BACKLOG_navigator-viz` (76/24) · `REQ-08` (296/151) · `SPEC_DELIVERY_LOOP` (146/125) ·
`SESSION_LEDGER` (71/67) · `REQ-02` (216/215) · `REQ-04` (192/191) · `REQ-11` (96/96) · `REQ-12` (99/99) ·
`REQ-13` (64/64). Local ≥ origin lines throughout → local is newer/superset; confirm no origin-only para lost.

## Procedure (step 1 — unify locally)

> Runs entirely in the isolated worktree `/private/tmp/reconcile-main` (branch
> `chore/reconcile-local-origin-main`, created off pin `bf8b5b58`). The **primary tree is never touched**.

1. **Pin & snapshot.** Record `main` tip (`bf8b5b58`) + `origin/main` tip (`7d2e4e18`). (Done — this worktree.)
2. **Dry-run the merge (read-only).** `git merge --no-commit --no-ff origin/main`; inspect. Expect the 12
   conflicts, 93 clean. Do NOT commit yet.
3. **Resolve the 12.**
   - 3 code files: open each, take local, but read origin's hunk to confirm it carried no unique fix
     (esp. `view_definition.py` vs #479). `git checkout --ours <file>` then eyeball.
   - 9 docs: take local (superset); grep for any origin-only paragraph before accepting.
4. **Commit the merge** on the branch (a real merge commit, both parents).
5. **Verify the merged tree** with `PYTHONPATH=<wt>/src`:
   - full `pytest` (or at least navigator+wireframe+coverage_map+validators+languages) green;
   - `ruff check src/`; byte-identity + navigator dogfood parse-integrity;
   - **import + smoke the newly-merged origin work** (`startd8 validate --help`, coverage-map, rule-catalog)
     — they've never coexisted with local's tree before.
6. **Re-check the moving target.** `git fetch`; confirm nothing critical landed that changes a resolution.
7. **Land to local `main`** via the safe cadence (§6). Stop here — publishing to origin is §7.

## §6 — Landing to local `main` safely

- Merge is **additive** (a merge commit on top of `bf8b5b58` with `origin/main` as second parent) — it does
  **not** rewrite the 139 local SHAs, so `feat/navigator-fr6-fr8-grounding`, `feat/navigator-req16-...`, and
  every other worktree keep their merge-base and still apply. (This is why MERGE, not rebase.)
- Land only if local `main`'s tip is **still `bf8b5b58`** at land time (`git merge-base --is-ancestor` check).
  If it advanced: re-merge the small new delta in the worktree, re-verify, then land. Never `reset`/`checkout`
  the shared primary tree; FF it to the reconciled commit only when it's a clean descendant.
- Do the land from the worktree via FF; restore the primary checkout to `main` afterward.

## §7 — Publish to origin (DEFERRED — separate decision)

Once local `main` is unified and green, decide whether to push the unified history to `origin` (KNOT 3). If yes:
worktree off `origin/main`, verify `merge-tree` clean, FF-push to `origin/main` — **never force-push**, and
only after the other agents whose commits ride along are aware. Not part of step 1.

## Rollback

- Any step before §6 land: `git worktree remove` the reconcile worktree — the primary tree and local `main`
  are untouched (nothing was committed to them).
- After §6 land, before §7 publish: local `main` has a new merge commit but origin is untouched; revert the
  merge commit locally if needed. Origin only changes in §7.

## Verification gates (all must pass before §6 land)

- [ ] `git merge` resolves to the 12 expected conflicts, 93 clean (no surprise conflict)
- [ ] each of the 3 code files: local taken, origin hunk read, no unique origin fix dropped
- [ ] full test suite green under pinned `PYTHONPATH`
- [ ] ruff clean; byte-identity self-comparison unedited; navigator dogfood parses
- [ ] newly-merged origin work (validate / coverage-map / rule-catalog) imports + smoke-tests
- [ ] primary `main` tip re-checked; land only if still a clean FF
