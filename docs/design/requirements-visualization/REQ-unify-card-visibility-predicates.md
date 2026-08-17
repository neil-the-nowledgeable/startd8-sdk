# Unify the navigator card-visibility filters into one composable predicate model — Requirements

**Project:** startd8-sdk (requirements visualization ladder) · **Criticality:** medium
**Version:** 0.2 (post-planning — draft→plan-against-code→reflect) · **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** the profiled navigator card browse (`src/startd8/wireframe_view/_template.py`)
**Inherits standards:** det-req-kit · NODE-SCHEMA · NAMING_CONVENTION · SOTTO_DESIGN_PRINCIPLE · REQ-view-definition-mode-and-control-consolidation (the definition-owned control taxonomy) · the node-fields distillation `ce6ed667` (structured `item.fields`) — this spec is the **INTERACTION-layer** distillation twin of that **DATA-layer** distillation
**Audience:** operator / requirement reader
**Trust boundary:** local render only · no network · no LLM · every predicate is computed client-side from the already-embedded `#plan-data` payload — no new data leaves the page
**Data classification:** internal

> **DIDL identity (document)** — not an integer phase brand:
> - **Semantic name:** Unify the navigator card-visibility filters into one composable predicate model where status, search, paging and audience-lens each contribute an independent hide-reason and a single recompute point pages the survivor set
> - **Local key (initiative):** `FEAT-navigator-unify-visibility-predicates`
> - **Canonical ref (planned):** `cc:intent:navig8r:interaction:visibility-predicates`
> - **Readable handle:** `feature/navigator-unify-visibility-predicates`
> Product capability ≠ code capability-index.

---

## 0. Planning Insights (Self-Reflective Update)

> This is a **reflective** spec, and MOVE 3 of the navig8r two-sided-coin strategy: the ENABLER move
> that makes the interaction layer compose cleanly BEFORE audience-tiering (Move 2) and search plug in —
> and it fixes a real, currently-live bug on the way. The v0.1 draft assumed "just make `pagedCards()`
> respect `pf-hidden`." Planning against the ACTUAL `_template.py` falsified that as too narrow: the
> defect is a *symptom* of accreted per-handler hide-toggles with no single composition point. Every row
> below is grounded in a real discovery (file:line), and every FR downstream is shaped by it.

| v0.1 Assumption | Planning Discovery (grounded) | Impact |
|-----------------|-------------------------------|--------|
| The bug is a one-line `pagedCards()` fix — patch it and move on | `pagedCards()` (`_template.py:1365-1368`) selects **all** `#outline .item` minus `.vd-template` with **no** `.pf-hidden` check, so status and paging already fail to intersect on the paged count. But the ROOT is structural: status hides via `_applyFilter`→`pf-hidden` (`:721-739`), paging hides via `applyPaging`→`pg-hidden` (`:1369-1393`), each an ad-hoc toggle by its own handler with **no shared composition point**. | **FR-1/FR-3:** don't patch one handler — introduce ONE `applyVisibility()` recompute point + a documented set of independent hide-reason classes; `pagedCards()` narrowing (**FR-4**) is then the bug fix that falls out for free. |
| Status and paging can just share one hide-class | They must NOT. `_applyFilter` clears/sets `pf-hidden` on every card each call (`:724-727`); `applyPaging` clears/sets `pg-hidden` on every card each call (`:1373`,`:1380`). If they shared a class, one owner's recompute would **clobber** the other's decision. | **FR-2:** keep the hide-reasons as **distinct classes** (`pf-hidden`/`pg-hidden`/future `srch-hidden`/audience) — each owner sets ONLY its own; visibility is the *union* of active reasons, so no owner can erase another's. |
| Paging pages the status-filtered set already | It does NOT (this is the live bug). `pagedCards()` (`:1365-1368`) ignores `pf-hidden`; toggle a status chip and the pager still counts hidden cards, so "showing X–Y of N" lies and paged windows include filtered-out rows. | **FR-4:** `pagedCards()` returns the **SURVIVOR set** — cards carrying no *pre-paging* hide-reason (not `pf-hidden`, not `srch-hidden`, not audience) — so paging composes with status (and future search) coherently. This IS the bug fix. |
| The audience/fluency lens already filters cards | It does not. `cur = role+"|"+flu` drives `resolveVM` (`:563-576`,`:1077`) which RE-RENDERS the whole outline from a different variant (~24 `flu`/`role` refs); it is not a per-card visibility predicate, and the new surfaces (doc-context band `:682`, detail peek `:887`) carry **0** audience refs. | **NR + FR-5:** the audience lens stays a re-render, NOT folded into `applyVisibility` here; but the unified model exposes a **documented SEAM** so Move 2's audience-per-card predicate (and search's `srch-hidden`) plug in at ONE place, by construction. |
| The recompute just needs to run once on toggle | It must survive re-renders. `renderAll()` rebuilds every card and calls `_pagingHook` (`:566`,`:1097`) so paging re-applies after a lens/depth toggle; `_applyFilter` resets `_activeFilter=null` on re-render (`:1073`). | **FR-3/FR-6:** `applyVisibility()` is the recompute called by every predicate owner AND from the `renderAll`/`_pagingHook` path, so the composed visibility survives a variant re-render exactly as paging does today. |
| Frame-mode / full-view / detail-peek are also card filters to fold in | They are NOT per-card row filters. `frame-bare`/`scaffold` (`:162`,`:192`) are frame *modes* (hide region content), `fullview-open` (`:480`) is a full-page *route*, `cd-open` (`:984`) is a per-card detail *expansion*. None is a "which cards are in the browse" predicate. | **NR (non-goals):** these are explicitly OUT of the predicate model — folding them in would conflate visibility-of-rows with mode/route/expansion state. |

**Resolved open questions:**
- **OQ-compose → conjunction of independent predicates.** A card is visible iff it carries NO active hide-reason; status ∧ search ∧ page ∧ (future) audience are ANDed, each contributing its own class.
- **OQ-one-class-or-many → many distinct classes, one recompute.** Distinct hide-reason classes (no clobbering) + one `applyVisibility()` composition point (single source of truth for "is this card shown").
- **OQ-bug-scope → the `pagedCards()` survivor-set narrowing IS the bug fix**, and it is the natural consequence of the unified model, not a separate patch.
- **OQ-audience-now → NO.** Audience-lens stays a re-render in this move; the model only exposes the SEAM. Move 2 delivers the audience predicate through that seam.
- **OQ-byte-identity → all machinery is `payload.profile`-gated / `body.nav-profiled`-only**; the app-scaffold path (no profile) applies no filter classes, so `applyVisibility()`/`pagedCards()` narrowing are no-ops and the output is byte-identical.

---

## Overview

The navigator card browse (`#outline`) already has several independent ways to hide a card — the PF-1
status chips (`pf-hidden`), the paging group (`pg-hidden`), and soon free-text search (`srch-hidden`)
and an audience-per-card predicate (Move 2). Today each is an **ad-hoc hide-class toggled by its own
handler with no single composition point**, and the proof is a real bug: `pagedCards()` selects every
card regardless of `pf-hidden`, so **status filtering and paging don't intersect** — the pager counts
and pages cards the status filter has hidden.

This move distills that accreted machinery into ONE **composable predicate model**. Each filter
contributes an **independent hide-reason** (its own distinct class, so no owner clobbers another's
decision); a single **`applyVisibility()`** recompute point is the one source of truth for whether a
card is shown (a card is visible iff it carries **no** active hide-reason class); and `pagedCards()` is
narrowed to the **survivor set** so paging pages exactly the cards the other predicates left visible —
which **fixes the bug**. The model exposes a documented **seam** so a new predicate (search's
`srch-hidden`, Move 2's audience predicate) plugs in at one place, and future filters compose *by
construction*, not by patching every handler.

Strategically this is the ENABLER rung of the navig8r two-sided coin: the interaction layer must
compose cleanly before audience-tiering and search ride on it. It is behaviour-preserving **except**
the bug fix (status now correctly affects the paged count), and it is entirely profiled-navigator-only:
the deterministic app-scaffold path stays byte-identical.

---

## Objectives

- **O-1 — One composition point.** There is a single `applyVisibility()` recompute that is the sole authority for whether a card is shown; a card is visible iff it carries no active hide-reason class.
- **O-2 — Independent, non-clobbering hide-reasons.** Each predicate owns a distinct hide-reason class and sets only its own, so predicates compose (AND) without erasing each other's decisions.
- **O-3 — Fix the status↔paging bug.** Paging pages the survivor set, so status filtering correctly affects the paged window and the "showing X–Y of N" count.
- **O-4 — A documented seam for new predicates.** Adding a predicate (search, audience) is a one-place change: register its hide-reason and let `applyVisibility()` compose it — no per-handler patching.
- **O-5 — Behaviour-preserving + byte-identical app path.** No user-visible behaviour changes except the bug fix; with no profile the app-scaffold render is byte-identical.

---

## Risks

| ID | Risk | Mitigation |
|----|------|------------|
| RK-1 | Refactoring `_applyFilter`/`applyPaging` into a shared model regresses the working status filter or paging | Behaviour-preserving refactor with the existing `data-status`/chip and paging tests as the parity guard; `applyVisibility()` reproduces the current union semantics before any narrowing |
| RK-2 | A shared hide-class causes one owner to clobber another's decision (the very failure being fixed) | FR-2 keeps the classes **distinct**; each owner touches only its own class; visibility is the union — structurally impossible to clobber |
| RK-3 | `pagedCards()` narrowing changes the paged count in a way that surprises (it is a behaviour change, however correct) | Documented as the ONE intended behaviour change (O-3); covered by a test asserting a status-hidden card is excluded from N |
| RK-4 | The recompute doesn't survive a lens/depth re-render (paging/filter reset) | FR-3/FR-6 wire `applyVisibility()` into the `renderAll`/`_pagingHook` path exactly as `applyPaging` is today (`:1097`) |
| RK-5 | The seam is under-specified and Move 2/search re-patch handlers anyway | FR-6 requires the seam be documented in-code (one registration shape) with the existing predicates expressed THROUGH it as the worked examples |
| RK-6 | App-scaffold path drifts from byte-identity | FR-7 gates all machinery on `payload.profile`; guarded by `test_no_profile_is_byte_identical` |

---

## Profile

**internal** — a renderer-internal interaction-layer refactor of the profiled navigator. No new CLI
surface, no new payload fields, no network, no LLM. The observable deltas are (a) the bug fix (status
affects the paged count) and (b) an in-code seam for future predicates. All behaviour is client-side JS
in the embedded `_template.py` view, active only under `payload.profile`.

---

## Functional Requirements

- **FR-1 — Single visibility recompute point.** Introduce one `applyVisibility()` function that is the sole authority for card visibility, deriving each card's shown/hidden state from the union of its active hide-reason classes and recomputing section-emptiness from that union. Name: A single applyVisibility recompute point derives every card's visibility from the union of its active hide-reason classes. Touches: `code: src/startd8/wireframe_view/_template.py`. Verify: after any predicate change, every `#outline .item` with no active hide-reason class is displayed and every one with at least one is `display:none`. Serves: O-1
- **FR-2 — Independent non-clobbering hide-reason classes.** Keep the hide-reasons as distinct classes (`pf-hidden` for status, `pg-hidden` for paging, reserved `srch-hidden` for search, reserved audience class for Move 2), each set ONLY by its owning predicate, so composing predicates is a union that no owner can erase. Name: Each predicate owns a distinct hide-reason class it alone sets so predicates compose without clobbering. Touches: `code: src/startd8/wireframe_view/_template.py`. Verify: `_applyFilter` toggles only `pf-hidden` and `applyPaging` toggles only `pg-hidden`; toggling a status chip while paged leaves the paging class decisions intact and vice-versa. Serves: O-2
- **FR-3 — Status predicate routes through the model.** Refactor `_applyFilter`/`_onChipClick` (`_template.py:721-744`) so the status filter sets its own `pf-hidden` class and then calls `applyVisibility()` for the composed recompute, preserving the existing toggle-to-clear and empty-section-collapse behaviour. Name: The status filter sets only pf-hidden then defers the composed recompute to applyVisibility. Touches: `code: src/startd8/wireframe_view/_template.py`. Verify: clicking a status chip hides exactly the non-matching cards and re-clicking it restores all, identical to today, with `applyVisibility()` on the call path. Serves: O-1
- **FR-4 — Page the survivor set (fixes the bug).** Narrow `pagedCards()` (`_template.py:1365-1368`) to return only survivor cards — real cards (not `.vd-template`) carrying no pre-paging hide-reason (`:not(.pf-hidden):not(.srch-hidden)` and no active audience class) — so paging composes with status and the "showing X–Y of N" count reflects the filtered set. Name: pagedCards returns only the survivor set of the pre-paging predicates so paging composes with status. Touches: `code: src/startd8/wireframe_view/_template.py`. Verify: with a status chip active and page size 5, a `pf-hidden` card is excluded from the pager total N and never appears in a page window. Serves: O-3
- **FR-5 — Documented seam for a new predicate.** Expose one documented in-code seam (a single place naming the ordered set of hide-reason classes `applyVisibility()` composes) so a new predicate — search's `srch-hidden`, Move 2's audience predicate — is added by registering its class there and having its owner call `applyVisibility()`, with no edit to any other predicate's handler. Name: A documented single-place seam lets a new predicate compose by registering its hide-reason not by patching handlers. Touches: `code: src/startd8/wireframe_view/_template.py`. Verify: the reserved `srch-hidden` and audience classes appear in the survivor selector and the seam comment enumerates the composed hide-reasons in one place. Serves: O-4
- **FR-6 — Recompute survives re-render.** Wire `applyVisibility()` into the `renderAll`/`_pagingHook` path (`_template.py:1097`,`:1396`) so after a lens/depth variant re-render the composed visibility (status ∧ page) is re-derived exactly as paging is re-applied today. Name: applyVisibility re-runs through the renderAll paging hook so composed visibility survives a variant re-render. Touches: `code: src/startd8/wireframe_view/_template.py`. Verify: setting a page size then toggling the audience/fluency lens leaves the pager window and any active status filter correctly composed after the re-render. Serves: O-1
- **FR-7 — App-scaffold byte-identity.** Keep all predicate-model machinery profiled-navigator-only: with no `payload.profile`, no hide-reason class is ever applied, so `applyVisibility()` and the `pagedCards()` survivor narrowing are no-ops and the app-scaffold render emits not one changed byte. Name: The whole predicate model is profile-gated so the app-scaffold render stays byte-identical. Touches: `code: src/startd8/wireframe_view/_template.py`, `test: tests/unit/wireframe/test_render_profile.py`. Verify: `test_no_profile_is_byte_identical` (`:34-36`) stays green — `render_html(_plan()) == render_html(_plan(), profile=None)`. Serves: O-5

---

## Non-Goals

- **NG-1 — No audience-per-card predicate here.** The audience/fluency lens (`cur = role+"|"+flu`, `resolveVM` `:563-576`) stays a full-outline re-render in this move; folding it into `applyVisibility()` as a per-card predicate is **Move 2**, which rides the FR-5 seam.
- **NG-2 — No free-text search delivery here.** Search's live filter and `data-search` blob are `REQ-freetext-search-on-navigator-card-browse.md`; this move only reserves its `srch-hidden` class in the seam (see Coordination).
- **NG-3 — Frame/route/expansion state is out of the model.** `frame-bare`/`scaffold` (`:162`,`:192`), `fullview-open` (`:480`), and `cd-open` (`:984`) are frame-mode / full-page-route / detail-expansion state, NOT per-card row predicates, and are not folded in.
- **NG-4 — No behaviour change beyond the bug fix.** The only intended user-visible delta is that status now correctly affects the paged count/window; everything else is a behaviour-preserving refactor.
- **NG-5 — No new payload fields or CLI surface.** No changes to `#plan-data`, the profile schema, or any `startd8` command.

---

## Owned Fields

This move owns no new **payload** fields — it is an interaction-layer refactor over existing render
state. It owns the following in-code interaction-layer contract (client-side, `_template.py`):

| Owned symbol | Kind | Meaning |
|--------------|------|---------|
| `applyVisibility()` | JS function | the single visibility recompute; sole authority for card shown/hidden + section-emptiness |
| hide-reason class set | CSS class contract | `pf-hidden` (status) · `pg-hidden` (paging) · reserved `srch-hidden` (search) · reserved audience class (Move 2) — each owned by exactly one predicate |
| survivor selector | JS selector | `pagedCards()`'s pre-paging survivor filter (`:not(.pf-hidden):not(.srch-hidden)` + audience) — the one place paging reads the composed set |
| predicate seam | in-code doc | the single enumerated registration point new predicates plug into |

---

## Contract Projection (entry table)

| Entry | Projects to | Shape |
|-------|-------------|-------|
| `applyVisibility()` | `_template.py` client JS | pure recompute over `#outline .item` class-union → `display` + section `pf-empty`/`pg-empty` |
| status predicate | `_applyFilter`/`_onChipClick` (`:721-744`) | sets `pf-hidden` only → calls `applyVisibility()` |
| paging predicate | `applyPaging`/`pagedCards` (`:1365-1393`) | reads survivor set; sets `pg-hidden` only |
| re-render hook | `_pagingHook`/`renderAll` (`:1097`,`:1396`) | re-invokes `applyVisibility()` after variant rebuild |
| seam | in-code enumerated hide-reason registration | new predicate registers class + calls `applyVisibility()` |
| byte-identity guard | `tests/unit/wireframe/test_render_profile.py::test_no_profile_is_byte_identical` | profile=None ⇒ identical output |

---

## Coordination

`REQ-freetext-search-on-navigator-card-browse.md` **FR-5** already proposes fixing the SAME
`pagedCards()` status↔paging bug (`_template.py:1365-1368`) as the seam its `srch-hidden` predicate
rides on. State plainly:

- **MOVE 3 SUBSUMES that fix.** The `pagedCards()` survivor-set narrowing lives here (FR-4) as the
  natural consequence of the unified model, not in the search delivery.
- **Recommended operator sequence: Move 3 → search → Move 2.** Land Move 3 FIRST so `applyVisibility()`
  + the survivor selector + the documented seam exist. Then the search delivery **consumes the seam** —
  its `srch-hidden` becomes one registered predicate that sets its own class and calls
  `applyVisibility()`, rather than re-patching `pagedCards()`/`applyPaging`. Then Move 2's audience
  predicate plugs into the same seam.
- **Redirect for the search spec once Move 3 lands:** search's FR-5 collapses from "narrow `pagedCards()`
  + repair the status↔paging non-intersection" to "register `srch-hidden` in the seam" — the paging
  repair is already done. FR-4 of search (intersect with status) is likewise satisfied by construction.

---

## Iterations (acyclic)

| Iteration | Delivers | Depends on | FRs |
|-----------|----------|------------|-----|
| **It-1** | Introduce `applyVisibility()` reproducing today's union semantics (parity, no behaviour change) | — | FR-1, FR-2 |
| **It-2** | Route the status predicate (`_applyFilter`/`_onChipClick`) through `applyVisibility()` | It-1 | FR-3 |
| **It-3** | Narrow `pagedCards()` to the survivor set — the bug fix | It-2 | FR-4 |
| **It-4** | Document the seam (enumerated hide-reasons + reserved `srch-hidden`/audience classes) | It-3 | FR-5 |
| **It-5** | Wire `applyVisibility()` into the `renderAll`/`_pagingHook` re-render path | It-4 | FR-6 |
| **It-6** | Byte-identity guard green (profile=None no-op) | It-5 | FR-7 |

---

## Appendix A — Grounding index (file:line)

| Machinery | Location | Role in this move |
|-----------|----------|-------------------|
| Status filter | `_applyFilter`/`_onChipClick` `_template.py:721-744` | routes through `applyVisibility()` (FR-3) |
| `.item.pf-hidden{display:none}` | `_template.py:508` | the status hide-reason class (kept distinct) |
| `data-status` stamp | `renderItem` `_template.py:936-937` | the datum the status predicate reads |
| Paging | `applyPaging` `_template.py:1369-1393` | pages the survivor set (FR-4) |
| `pagedCards()` (the bug) | `_template.py:1365-1368` | selects ALL `.item` minus `.vd-template`, ignores `pf-hidden` — narrowed to survivors |
| `.pg-hidden` | `_template.py:417` | the paging hide-reason class (kept distinct) |
| `_pagingHook`/`renderAll` | `_template.py:1097`,`:1396` | the re-render path `applyVisibility()` joins (FR-6) |
| Audience/fluency lens | `cur`/`resolveVM` `_template.py:563-576`,`:1077` | stays a re-render; seam target for Move 2 (NG-1) |
| Frame/route/expansion (out) | `frame-bare` `:162`,`:192` · `fullview-open` `:480` · `cd-open` `:984` | explicitly not predicates (NG-3) |
| Byte-identity guard | `tests/unit/wireframe/test_render_profile.py:34-36` | FR-7 |

## Appendix B — The essential vs accidental complexity

- **Essential:** a card's visibility is a **conjunction of independent predicates** (status ∧ search ∧
  page ∧ audience). That conjunction is irreducible — it is what "which cards do I see" means.
- **Accidental (accreted):** each predicate was added as its own ad-hoc hide-class toggled by its own
  handler with **no single composition point**, so they don't intersect correctly. The `pagedCards()`
  bug is the *proof* — paging simply never learned about the status predicate.
- **The distillation:** one recompute point + distinct non-clobbering hide-reasons + a survivor-set
  selector + a documented seam. After this, composing predicates is a *union of classes at one point*,
  and adding a predicate is a *one-place registration* — the accidental complexity (N handlers each
  knowing about the others) is gone.

## Appendix C — Twin of the node-fields distillation `ce6ed667`

`ce6ed667` distilled the **DATA layer** (structured `item.fields` read BY KEY, no prose reparse). This
move is its **INTERACTION-layer** twin: distill the visibility machinery to structured, composable
predicates read at ONE point, no per-handler re-patch. Same shape — replace N ad-hoc sites with one
typed authority — applied one layer up the stack.
