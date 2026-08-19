# Enhancement Backlog — REQ-cross-surface-view-definition (CEP / HTH harvest)

**Subject:** shipped cross-surface View Definition (`node_state` + `surface_links` on the existing
cascade; navig8r projection equality-gated). **Generated:** 2026-08-19 via CEP as HTH stage-7 Phase 4.
**Tree:** worktree `/private/tmp/wt-hth-cross-surface`, branch `hth/cross-surface-view-definition`
(HTH-1 `7ca8a5f2` on top of RECORD `7b211478`). Lands via Spec Delivery Loop **local ff-only**, not
an origin PR (this repo's loop convention; CEP Phase-4 "open a PR" is the same reviewable commits).

> Selection of S/M/L is **human-owned**. XS / clearly-mechanical-S auto-executed this run (annotated
> `→ landed`). Re-ground each remaining `fix` against the tree before building (CL-29).

## Provenance / prior-art manifest (Phase 0)

Greps run (2026-08-19, this worktree):

```
rg -l 'ENHANCEMENT_BACKLOG' docs/design/requirements-visualization
rg -n -i 'cross-surface|node_state|surface_links' docs/design/requirements-visualization/*ENHANCEMENT_BACKLOG*
rg -n 'surface_links|presentation.cockpit' src/startd8/kickoff_experience
rg -n '_navig8r_statuses_from_node_state|_status_specs|validate_definitions' src/startd8
```

**Found (do not duplicate):**
- `ENHANCEMENT_BACKLOG_req10-view-definition.md` — EC-1 CLI dump, EC-4 `definition_diff`, EC-6
  `validate_definitions` (extends + **chrome.bindings only**), EC-7 HOWTO, EC-8 theme activation,
  EC-9 NODE-VIEW-SCHEMA. This file is the **first** cross-surface backlog; REQ-10 rows stay there.
- `ENHANCEMENT_BACKLOG_navigator-viz.md` — cleared (EB-1..3, R8 rows). No `node_state` hits.
- `ENHANCEMENT_BACKLOG_req07-diff.md`, `ENHANCEMENT_BACKLOG_det-plan-projector.md` — unrelated.
- Ledger harvest **H1 cockpit adopter** (`SESSION_LEDGER` follow-ups) — already named. Refined as
  first-bricks below; **not** re-mined as a new M-spec.

**Code-grounding (CL-29) at generation time:**
- HTH subset-as-opt-in hole **closed** (`view_definition.py:264` `==`; tests
  `test_hth_proper_subset_of_canonical_keys_is_not_an_opt_in` / empty-vocab / malformed-leaf).
- `kickoff_experience/` **0** matches for `surface_links` / `node_state` (NR-7 — not a defect).
- `validate_definitions` (`:691-712`) still silent on `surface_links.via` — **open**.
- Dual-write vocab vs `presentation.navig8r` had **no equality test** at harvest start — **open**
  (XS pin this run).

**CEP run shape:** 3 independent seeders (A wiring / B defect-first / C operator-governance) →
1 cumulate round (orchestrator CROSS/VARY) → triage. **Triage-surviving off-seed count (R-4): 4**
crossovers (EC-CS-1, EC-CS-2, EC-CS-3, EC-CS-4) — CEP earned its keep (>0).

## Ranked backlog

| ID | Title | Val×Eff | Type | Byte-safe | Lineage |
|----|-------|---------|------|-----------|---------|
| **EC-CS-2** | **Pin dual-write oracle** — when keys equal, each `REQUIREMENTS_DEFINITION.vocabulary.statuses[k]` must equal `node_state.states[k].presentation.navig8r` (the side `_status_specs` actually reads) | **XS** | fix | ✅ | CROSS(B1+C2) — **→ landed this run** |
| **EC-CS-5** | **HOWTO: equal-keys opt-in + inherited `node_state`/`surface_links`** — a new domain that reuses the five canonical ids silently drops its own labels; a thin delta **inherits** drill/rollup/cockpit leaves | **XS** | docs | ✅ | VARY(B6)+C6 HOWTO inherit — **→ landed this run** |
| **EC-CS-6** | **CLI dump / `--from` pins inherited `node_state` + `surface_links`** — EC-1 tests currently assert theme/vocab/chrome only | **XS** | wire-existing | ✅ | C3 — **→ landed this run** |
| **EC-CS-1** | **`validate_definitions` walks resolved `surface_links.via`** — `via` ∈ `regions.bindings` **or** the known primitive `serves`; typed shape `{from_surface, to_surface, relation, via}` with `relation ∈ {drill, rollup}`; cockpit `attention` ∈ `{ok, review, blocked, backlog}` without importing `kickoff_experience` | **S** | wire-existing | ✅ | CROSS(A3+B2+C1) — judgment: allowed `via` set (region vs primitive) |
| **EC-CS-3** | **Public cockpit projector** (symmetric to `_navig8r_statuses_from_node_state`) — skip `kind: project`; **do not ship without a caller** (would mint a dormant) | **S** | wire-existing | ✅ | CROSS(A2+B4) — first brick of ledger H1, not the tile rebuild |
| **EC-CS-4** | **Structured drill `href: "#{key}"` field** on `surface_links.drill` (or project into existing `cross_links` when a base URL is supplied) — today `via: fullview` is a name; the `#<key>` contract lives in region scaffold **prose** | **S** | wire-existing | ✅ | CROSS(A1+B3) — H1 first brick; `portal_spec.py` stays NR-7 |
| **EC-CS-9** | **`--validate` fail-closed on malformed presentation leaves** — projection skip of a non-dict navig8r leaf stays (FR-7); `--validate` must not stay green | **S** | fix | ✅ | C4 — pairs with EC-CS-1 |
| **EC-CS-8** | **Shared cockpit colors** — opt-in: `_ATTENTION_DISPLAY` / `_BADGE` read `presentation.cockpit.color`; fallback keeps current glyphs | **S** | wire-existing | ✅ | A6 — touches `kickoff_experience/` (H1-adjacent; NR-7 until adopter) |
| **EC-CS-7** | **FR-5 consumer: node_state → existing `_rollup` / activation** — map navig8r status through `presentation.cockpit.attention`, feed worst-case `_rollup` + `attention_counts` | **M** | wire-existing | ⚠️ cockpit-visible | A5 — sibling of ledger **H1**, not a substitute |
| **H1** | **Cockpit adopter spec** — tiles read `surface_links` and link `#<key>` | **M** | author-spec | n/a | ledger (already named) — author via `/reflective-requirements` |

### Wildcard (single-seeder, no descendants)

| ID | Title | Val×Eff | Note |
|----|-------|---------|------|
| **EC-CS-10** | **`--validate` advisory: `surface_links` + `presentation.cockpit` declared-not-consumed** | S | C5 — exit 0 (dormancy is the spec). Stops `ok: N definitions valid` being read as "drill is live." |

## Absorbed seeds (not standalone rows)

Seeder A "H1 refined opt-in cockpit-row drill hrefs" and seeder B "declare cockpit display copy on
the same leaves" fold into **H1** / **EC-CS-8**. Seeder C "Verify + HOWTO, do not grow `govern.py`"
folds into **EC-CS-5** + a note: `govern.py` NR-6 still forbids a 6th corpus check; definition
governance stays on `view-definition --validate`.

## Honesty note

Seeders read spec + code and cited `file:line`. **Verify before building.** EC-CS-2/5/6 were
code-grounded and landed this harvest. EC-CS-1 is the highest-value remaining row (extends the
shipped EC-6 seam). Do **not** auto-apply EC-CS-3 until it has a non-test caller.
