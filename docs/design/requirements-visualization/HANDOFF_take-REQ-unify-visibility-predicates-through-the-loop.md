# Handoff — Take the visibility-predicate distillation (Move 3) through the Spec Delivery Loop

**For:** the loop operator (a separate implementation session), cold. **Written:** 2026-08-17.
**Goal:** build Move 3 — unify the card-visibility interaction layer into one composable predicate model —
via the 7-stage Spec Delivery Loop, under the repo's discipline. Self-contained.

---

## 0. What you're building (one paragraph)

Card visibility is a conjunction of independent predicates — `status ∧ search ∧ page ∧ audience-lens` — but
today each is an ad-hoc hide-class toggled by its own handler with **no single composition point**, so they
don't intersect (the `pagedCards`↔`pf-hidden` bug). This move distills them into **one `applyVisibility()`
recompute point**, where each filter owns its own **non-clobbering** hide-reason class and `pagedCards()`
pages the **survivor set** (fixing the bug), plus a **documented seam** that future predicates (search,
audience) plug into by construction. Behaviour-preserving except the bug fix; profiled-navigator-only;
app-scaffold path byte-identical. It is the *interaction*-layer twin of the shipped *data*-layer distillation
(`ce6ed667`).

- **Spec:** `docs/design/requirements-visualization/REQ-unify-card-visibility-predicates.md` (7 FRs, BUILD-READY).
- **Strategy context:** `STRATEGY_navig8r-inflection-two-sided-validation.md` — Move 3 is the *enabler* for
  Move 2 (audience tiers) and search; navig8r validates **both** technical grounding **and** business value.

## 1. Preconditions (verify first)

```bash
python3 scripts/navigator_spec_delivery_loop.py \
  $(pwd)/docs/design/requirements-visualization/REQ-unify-card-visibility-predicates.md
# expect: BUILD-READY ✓ (7 FRs)
```

## 2. Coordination — this SUBSUMES the search REQ's FR-5

`REQ-freetext-search-on-navigator-card-browse.md` FR-5 proposes the SAME `pagedCards` survivor-set fix as
the seam search rides. **Land Move 3 FIRST**, then the search delivery consumes the unified `applyVisibility`
seam (its `srch-hidden` becomes one predicate) instead of re-patching paging. Recommended loop order:
**Move 3 → search → Move 2 (audience).** If you're about to run the search delivery and Move 3 is unbuilt,
build Move 3 first.

## 3. Build seams (grounded in the spec's §0 + FRs)

- **Today's machinery:** status `_applyFilter`/`_onChipClick`→`.pf-hidden` (`_template.py:721-744`, CSS `:508`);
  paging `applyPaging`/`pagedCards`/`_pagingHook`→`.pg-hidden` (`:1365-1396`, CSS `:417`).
- **The bug (verify):** `pagedCards()` (`:1365-1368`) selects all `#outline .item` (minus `.vd-template`) with
  no `.pf-hidden` check → status + paging don't intersect on the paged count.
- **Do NOT fold in** frame-mode (`frame-bare`/`scaffold`), the full-page route (`fullview-open`) or the detail
  peek (`cd-open`) — those aren't per-card-row filters (the spec holds them out as non-goals).
- **The seam:** one `applyVisibility()` recompute; each predicate sets only its own class; `pagedCards()`
  narrowed to the survivor set; a documented one-place hook to add a predicate. Audience-lens is re-render
  today — the seam should let Move 2 add it as a predicate without touching every handler.

## 4. Git cadence — the hot-main discipline (learned the hard way)

`main` is a **hot, contended ref** (it advanced *several times* during the session that authored this).
The primary worktree holds **other agents' uncommitted files** — never disturb them. `origin/main` is
**diverged** (missing the REQ-18..24 foundation) — do **not** push there.
- Work in a **worktree off local `main`**; pin `PYTHONPATH=<wt>/src`.
- Land with **`--ff-only`**: rebase onto the *current* `main`, re-check the tip immediately before merging,
  ff. If `main` moved, the ff fails safe — re-rebase and retry. Resolve rebase conflicts by **combining**.
- **Never force-push `origin`.** Add a `docs(viz): ledger —` entry on delivery.

## 5. Done-when

7/7 FRs verified (grounded, not asserted) · the three-way compose test (`status ∧ page`, then with search
once it lands) + the pagedCards-survivor **regression test** present · full navigator+wireframe suite green ·
app-path byte-identity held **unedited** · ruff clean · landed on local `main` via ff + a ledger entry.
