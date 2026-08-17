# Handoff — Take free-text card search through the Spec Delivery Loop

**For:** another session/agent (the *loop operator*) picking this up cold. **Written:** 2026-08-17.
**Goal:** build the free-text card-browse search via the 7-stage Spec Delivery Loop (LOOP_CATALOG #6),
under the repo's discipline (byte-identity, git cadence, concurrent-agent safety). Self-contained — you
should not need the originating conversation.

---

## 0. What you're building (one paragraph)

A **free-text search box** over the profiled navigator's requirement **card browse** (`#outline`): as the
reader types, cards whose structured text (key · name · statement · verify · Touches paths) don't match are
hidden in real time. It **composes** (intersects) with the two filters that already exist — the PF-1 status
chips and the paging group — so the visible set is always `status ∧ search ∧ page`. The control is
**definition-owned** (registered in the View Definition `control.groups` like paging was) and
**profiled-navigator-only**: with no `payload.profile` (the deterministic app-scaffold preview) not one byte
changes. It adapts the *proven* tree-renderer search pattern rather than inventing one.

- **Spec:** `docs/design/requirements-visualization/REQ-freetext-search-on-navigator-card-browse.md` (7 FRs,
  BUILD-READY, 6-iteration acyclic plan). DIDL handle `feature/navigator-card-freetext-search`.
- **Variant context:** `docs/design/requirements-visualization/VARIANT_STATUS_navigator-renderer-inventory.md`
  — search is the top "pull-in" gap (tree has it, the card view had 0).
- **The loop:** `scripts/navigator_spec_delivery_loop.py` + the runbook `SPEC_DELIVERY_LOOP.md`.

## 1. Preconditions (verify first)

```bash
cd /Users/neilyashinsky/Documents/dev/startd8-sdk      # or a worktree off local main
python3 scripts/navigator_spec_delivery_loop.py \
  $(pwd)/docs/design/requirements-visualization/REQ-freetext-search-on-navigator-card-browse.md
# expect: BUILD-READY ✓ (7 FRs) — name-block · frs-parse · frs-named · frs-verify · frs-serves all ✓
python3 scripts/navigator_spec_delivery_loop.py --checklist   # the 7 stages
```

## 2. The one non-obvious build fact (read FR-5 carefully)

Grounding surfaced a **pre-existing bug** the spec folds into scope: `pagedCards()`
(`_template.py:1365-1368`) selects **all** `#outline .item` with **no `.pf-hidden` check**, so the status
filter and paging **don't intersect today** (status-hidden cards still count toward the page window/total).
**FR-5 repairs this** — paging must page the *survivor set* (not `pf-hidden` and not the new `srch-hidden`).
So search rides a seam that also fixes a latent defect; write the guard test for the three-way compose
(`status ∧ search ∧ page`) and a negative test that a status-hidden card no longer counts toward N.

## 3. Build seams (all grounded in the spec's §0 + FRs)

- **Blob (FR-2):** build `data-search` structurally from `item.key` + `item.fields.name/statement/verify` +
  `item.touches[].path` (lowercased) — mirror `render_tree.py:_search_blob` (`:45-52`). NEVER a prose reparse
  (the `ce6ed667` distillation is what makes this honest).
- **Input + filter (FR-1/FR-3):** adapt `render_tree.py` `_TREE_JS` (`:326-345`) — `id`'d input, live `input`
  event, `.includes(term)` → toggle a **third** independent `srch-hidden` class (not `pf-hidden`/`pg-hidden`).
- **Compose (FR-4/FR-5):** `_applySearch` adds only `srch-hidden`; `_applyFilter` (`:721-739`) unchanged;
  narrow `pagedCards()` to exclude both hide-classes; re-page via `_pagingHook` from both `_applySearch` and
  `_onChipClick`.
- **Register (FR-6):** add a `search` group to `BASE_NAVIG8R_DEFINITION.control.groups` (mirror `paging`
  `:337-347`) + a `regions.bindings` entry with a `data-scaffold` role (mirror `detail`/`fullview` `:381-382`)
  so `applyDefinitionOverride` (`:1107-1122`) carries it.
- **Byte-identity (FR-7):** everything `payload.profile`-gated / `body.nav-profiled`-only;
  `tests/unit/wireframe/test_render_profile.py::test_no_profile_is_byte_identical` must stay green **unedited**.

## 4. Git cadence — the concurrent-agent discipline (learned the hard way this session)

**`main` is a HOT, contended ref** — during the session that authored this spec, `main` advanced **twice**
mid-work (`1f2a79d4` → `b7bf4c08` → `8ac4b49c`), driven by other agents landing REQ-22..27. Also: the
primary worktree carries *other agents' uncommitted files* — never disturb them; `origin/main` is **diverged**
(missing the REQ-18..24 foundation) — do **not** push there.

- **Work in a worktree off local `main`**, never the primary tree. Pin `PYTHONPATH=<wt>/src`.
- **Land with `--ff-only`** (no orphan-able merge commit): rebase onto the *current* `main`, re-check the tip
  immediately before merging, ff. If `main` moved, the ff fails **safe** — re-rebase and retry.
- Resolve the likely `sources_requirements.py` / `_template.py` rebase conflicts by **combining** (both sides
  add independent code), never by dropping either.
- **Never force-push `origin`.** Add a `docs(viz): ledger —` entry on delivery (`SESSION_LEDGER_specs-and-open-tasks.md`).

## 5. Done-when

7/7 FRs verified (grounded, not asserted) · full navigator+wireframe suite green · app-path byte-identity
held **unedited** · the three-way compose (`status ∧ search ∧ page`) guard test + the pagedCards-survivor
regression test both present · search control visible in `resolve(BASE_NAVIG8R_DEFINITION).control["groups"]`
· ruff clean · landed on local `main` via ff + a ledger entry.
