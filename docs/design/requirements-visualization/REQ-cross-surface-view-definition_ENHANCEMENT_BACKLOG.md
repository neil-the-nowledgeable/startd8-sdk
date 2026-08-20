# Enhancement Backlog — REQ-cross-surface-view-definition (CEP / HTH harvest)

**Subject:** shipped cross-surface View Definition (`node_state` + `surface_links` on the existing
cascade; navig8r projection equality-gated). **Generated:** 2026-08-19 via CEP as HTH stage-7 Phase 4.
**Tree at harvest:** `hth/cross-surface-view-definition` (HTH-1 `f36d44fa` on RECORD `7b211478`);
harvest commits landed on local `main` through `6378f5ae`. Follow-on EC-CS-1 is this increment.

> Selection of S/M/L is **human-owned**. XS / clearly-mechanical-S auto-executed at harvest (annotated
> with SHAs below). Re-ground each remaining `fix` against the tree before building (CL-29).

## Provenance / prior-art manifest (Phase 0)

Greps run (2026-08-19, harvest worktree):

```
rg -l 'ENHANCEMENT_BACKLOG' docs/design/requirements-visualization
rg -n -i 'cross-surface|node_state|surface_links' docs/design/requirements-visualization/*ENHANCEMENT_BACKLOG*
rg -n 'surface_links|presentation.cockpit' src/startd8/kickoff_experience
rg -n '_navig8r_statuses_from_node_state|_status_specs|validate_definitions' src/startd8
```

**Found (do not duplicate):**
- `ENHANCEMENT_BACKLOG_req10-view-definition.md` — EC-1 CLI dump, EC-4 `definition_diff`, EC-6
  `validate_definitions` (extends + **chrome.bindings**; **EC-CS-1 now also walks `surface_links.via`**),
  EC-7 HOWTO, EC-8 theme activation, EC-9 NODE-VIEW-SCHEMA. This file is the **first** cross-surface
  backlog; REQ-10 rows stay there.
- `ENHANCEMENT_BACKLOG_navigator-viz.md` — cleared (EB-1..3, R8 rows). No `node_state` hits.
- `ENHANCEMENT_BACKLOG_req07-diff.md`, `ENHANCEMENT_BACKLOG_det-plan-projector.md` — unrelated.
- Ledger harvest **H1 cockpit adopter** (`SESSION_LEDGER` follow-ups) — already named. Refined as
  first-bricks below; **not** re-mined as a new M-spec.

**Code-grounding (CL-29), re-checked 2026-08-19 before EC-CS-1 / before considering EC-CS-2:**
- HTH subset-as-opt-in hole **closed** (`view_definition.py` `set(vocab) == set(nav)`; tests
  `test_hth_proper_subset_of_canonical_keys_is_not_an_opt_in` / empty-vocab / malformed-leaf).
- `kickoff_experience/` **0** matches for `surface_links` / `node_state` (NR-7 — not a defect).
- `validate_definitions` walking `surface_links.via` — **closed this increment (EC-CS-1)**.
- Dual-write vocab vs `presentation.navig8r` — **already closed** as EC-CS-2 (`6378f5ae`,
  `test_hth_requirements_vocab_matches_navig8r_leaves`). Do not rebuild.

**CEP run shape:** 3 independent seeders (A wiring / B defect-first / C operator-governance) →
1 cumulate round (orchestrator CROSS/VARY) → triage. **Triage-surviving off-seed count (R-4): 4**
crossovers (EC-CS-1, EC-CS-2, EC-CS-3, EC-CS-4) — CEP earned its keep (>0).

## Ranked backlog

| ID | Title | Val×Eff | Type | Byte-safe | Lineage |
|----|-------|---------|------|-----------|---------|
| **EC-CS-2** | **Pin dual-write oracle** — when keys equal, each `REQUIREMENTS_DEFINITION.vocabulary.statuses[k]` must equal `node_state.states[k].presentation.navig8r` (the side `_status_specs` actually reads) | **XS** | fix | ✅ | CROSS(B1+C2) — **→ landed `6378f5ae`** (already built; see prep note below) |
| **EC-CS-5** | **HOWTO: equal-keys opt-in + inherited `node_state`/`surface_links`** | **XS** | docs | ✅ | VARY(B6)+C6 — **→ landed `619c79be`** |
| **EC-CS-6** | **CLI dump / `--from` pins inherited `node_state` + `surface_links`** | **XS** | wire-existing | ✅ | C3 — **→ landed `6378f5ae`** (same commit as EC-CS-2) |
| **EC-CS-1** | **`validate_definitions` walks resolved `surface_links.via`** — `via` ∈ `regions.bindings` **or** the known primitive `serves`; typed shape `{from_surface, to_surface, relation, via}` with `relation ∈ {drill, rollup}`; cockpit `attention` ∈ `{ok, review, blocked, backlog}` without importing `kickoff_experience` | **S** | wire-existing | ✅ | CROSS(A3+B2+C1) — **→ landed `1c29387f`** |
| **EC-CS-3** | **Public cockpit projector** (symmetric to `_navig8r_statuses_from_node_state`) — skip `kind: project`; non-test caller = `validate_definitions` attention walk | **S** | wire-existing | ✅ | CROSS(A2+B4) — **→ landed this increment** (`cockpit_statuses_from_node_state`) |
| **EC-CS-4** | **Structured drill `href: "#{key}"` field** on `surface_links.drill` + `resolve_surface_link_href` | **S** | wire-existing | ✅ | CROSS(A1+B3) — **→ landed this increment** |
| **EC-CS-9** | **`--validate` fail-closed on malformed presentation leaves** — projection skip of a non-dict navig8r leaf stays (FR-7); `--validate` must not stay green | **S** | fix | ✅ | C4 — **→ landed this increment** (pairs with EC-CS-1) |
| **EC-CS-8** | **Shared cockpit colors** — opt-in: `_ATTENTION_DISPLAY` / `_BADGE` read `presentation.cockpit.color` | **S** | wire-existing | ✅ | A6 — **→ landed this increment** (`cockpit_attention_colors` + kickoff badge CSS) |
| **EC-CS-7** | **FR-5 consumer: node_state → existing `_rollup` / activation** | **M** | wire-existing | ⚠️ cockpit-visible | A5 — sibling of ledger **H1**, not a substitute |
| **H1** | **Cockpit adopter spec** — tiles read `surface_links` and link `#<key>` | **M** | author-spec | n/a | ledger (already named) — author via `/reflective-requirements` |

### Wildcard (single-seeder, no descendants)

| ID | Title | Val×Eff | Note |
|----|-------|---------|------|
| **EC-CS-10** | **`--validate` advisory: `surface_links` + `presentation.cockpit` declared-not-consumed** | S | C5 — exit 0 (dormancy is the spec). Stops `ok: N definitions valid` being read as "drill is live." |

## EC-CS-2 prep (already built — do not rebuild)

Re-grounded 2026-08-19 against local `main` before any new dual-write work:

| Claim | Evidence | Verdict |
|-------|----------|---------|
| Vocab leaf == navig8r leaf when keys equal | `tests/unit/navigator/test_node_state_projection.py` `test_hth_requirements_vocab_matches_navig8r_leaves` | **SHIPPED** (`6378f5ae`) |
| Projection reads `node_state` values | `_status_specs` `==` gate + `test_fr2a_projection_reads_node_state_not_just_the_vocabulary_literal` | **SHIPPED** (`67051859` + HTH-1 `f36d44fa`) |
| HOWTO names the equal-keys trap | `HOWTO_author_domain_definition.md` “Equal-keys opt-in (trap)” | **SHIPPED** (`619c79be`) |
| Ledger implement row still says “subset” | `SESSION_LEDGER` implement row now says **equal** keys | **fixed at harvest** (`a97517cb`) — was stale, now current |

**Stale docs that looked like EC-CS-2 was still open (corrected this increment):**
- This backlog’s Phase-0 bullet still said dual-write was “open (XS pin this run)” — that was
  harvest-*generation* tense. Now cites `6378f5ae`.
- Header still named the deleted `/private/tmp/wt-hth-cross-surface` worktree — replaced with landed SHAs.

No remaining EC-CS-2 code to write. **EC-CS-1 / EC-CS-3 / EC-CS-4 / EC-CS-8 / EC-CS-9 landed.** Next
open S/M: **EC-CS-7** (rollup → activation) or author **H1** / wildcard **EC-CS-10**.

## Absorbed seeds (not standalone rows)

Seeder A "H1 refined opt-in cockpit-row drill hrefs" and seeder B "declare cockpit display copy on
the same leaves" fold into **H1** / **EC-CS-8**. Seeder C "Verify + HOWTO, do not grow `govern.py`"
folds into **EC-CS-5** + a note: `govern.py` NR-6 still forbids a 6th corpus check; definition
governance stays on `view-definition --validate`.

## Honesty note

Seeders read spec + code and cited `file:line`. **Verify before building.** EC-CS-2/5/6 were
code-grounded at harvest. EC-CS-1 extends the shipped EC-6 seam. Do **not** auto-apply EC-CS-3 until
it has a non-test caller.
