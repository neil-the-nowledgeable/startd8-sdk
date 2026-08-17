# Free-text search over the navigator requirement card browse — Requirements

**Project:** startd8-sdk (requirements visualization ladder) · **Criticality:** medium
**Version:** 0.2 (post-planning — draft→plan-against-code→reflect) · **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** the profiled navigator card browse (`src/startd8/wireframe_view/_template.py`)
**Inherits standards:** det-req-kit · NODE-SCHEMA · NAMING_CONVENTION · SOTTO_DESIGN_PRINCIPLE · REQ-view-definition-mode-and-control-consolidation (the definition-owned control taxonomy) · the node-fields distillation `ce6ed667` (structured `item.fields` — cards are searchable BY KEY, not a prose reparse)
**Audience:** operator / requirement reader
**Trust boundary:** local render only · no network · no LLM · the search index is built client-side from the already-embedded `#plan-data` payload — no new data leaves the page
**Data classification:** internal

> **DIDL identity (document)** — not an integer phase brand:
> - **Semantic name:** Free-text search over the navigator requirement card browse — a definition-owned control that filters cards by key/name/statement/verify/Touches, composing with the status filter and paging, profiled-navigator-only
> - **Local key (initiative):** `FEAT-navigator-card-freetext-search`
> - **Canonical ref (planned):** `cc:intent:navig8r:search:card-browse`
> - **Readable handle:** `feature/navigator-card-freetext-search`
> Product capability ≠ code capability-index.

---

## 0. Planning Insights (Self-Reflective Update)

> This is a **reflective** spec. The v0.1 draft assumed "add a search box to the card browse."
> Planning against the ACTUAL `_template.py` / `view_definition.py` / `render_tree.py` code
> falsified four assumptions before a line was written. Every row below is grounded in a real
> discovery (file:line), and every FR downstream is shaped by it.

| v0.1 Assumption | Planning Discovery (grounded) | Impact |
|-----------------|-------------------------------|--------|
| No filtering exists yet; search will BE the filter | The PF-1 **status-filter** chips already exist (`_applyFilter`/`_onChipClick`, `_template.py:721-744`; `data-status` stamped in `renderItem` `_template.py:936-937`; CSS `.item.pf-hidden{display:none}` `:508`) AND a **paging** group already exists (`applyPaging`/`_pagingHook`, `_template.py:1362-1396`; `.pg-hidden` `:417`). | **FR-4/FR-5:** search must **COMPOSE (intersect)**, not replace — a card is visible iff it survives status AND search AND paging. Search adds a THIRD independent hide-class, it does not reuse `pf-hidden`/`pg-hidden`. |
| Search is renderer-local — just add an `<input>` and a JS handler | The control taxonomy is **definition-owned**: `BASE_NAVIG8R_DEFINITION.control.groups` (`view_definition.py:312-348`) registers `view`/`overlays`/`debug`/`paging`; paging was added there as "the first FUNCTIONAL display capability the View Definition owns" (`:337-347`), and `applyDefinitionOverride` (`_template.py:1107-1122`) relabels groups/regions from the profile. | **FR-6:** the search control **registers in `control.groups`** (like `paging` did), and its region wires a `regions.bindings` entry with a `data-scaffold` role (mirror `detail`/`fullview` at `view_definition.py:381-382`). Not a bare template string. |
| I'll build a search blob by re-parsing the card's rendered prose / `.det` text | The `ce6ed667` distillation made fields **structured**: `item.fields` carries `name`/`statement`/`verify`/`serves`/`depends`/`wont`/`handle` read BY KEY (`fieldsToSd` `_template.py:824-841`, `recordEntries` `:858-873`); `item.touches` is a typed list `{kind,path}` (`touchesRows` `:875-881`); `item.key`/`item.label`/`item.status` are first-class. `render_tree.py:_search_blob` (`:45-52`) already builds its blob from structured node fields — the Mottainai shape to adapt. | **FR-2:** the per-card `data-search` blob is built **structurally from typed fields** (`key` + `fields.name/statement/verify` + `touches[].path`), never a prose reparse. One place, mirroring `_search_blob`. |
| Paging pages the status-filtered set already | It does NOT. `pagedCards()` (`_template.py:1365-1368`) selects **all** `#outline .item` (minus the display template) with no regard for `pf-hidden` — status filter and paging already fail to intersect on the paged count. | **FR-5 (sharpened):** paging must page the **survivor set** (not-status-hidden AND not-search-hidden). Fixing the paged set to respect the active filters is IN SCOPE for the search feature (it is the seam search rides on); the pre-existing status↔paging non-intersection is repaired as part of FR-5 so the three compose coherently. |
| The tree renderer's search is a different codebase to reinvent | `render_tree.py` (`:326-345`, `_TREE_JS`) already ships the exact pattern: an `id="q"` input, a `data-search` attribute per node, real-time `input` → substring `.includes(term)` → `style.display`. | **FR-1/FR-3:** adapt the proven `_TREE_JS` shape (lowercased substring, live `input` event) into the card browse — reuse, don't re-invent (Mottainai). Difference: card browse composes with two existing filters; the tree composes with parent/child visibility. |

**Resolved open questions:**
- **OQ-compose → intersection, not replacement.** Status filter, search, and paging are three orthogonal predicates ANDed together; clearing search restores the status-filtered+paged view, clearing status restores the searched+paged view.
- **OQ-blob-source → typed `item.fields`/`item.touches` BY KEY** (the distillation `ce6ed667` is what makes this honest — no prose reparse).
- **OQ-where-registered → `view_definition.py` `control.groups` + a `regions.bindings` entry**, not a hardcoded template string (REQ-14 lock).
- **OQ-byte-identity → the input + JS + blob are all `payload.profile`-gated / `body.nav-profiled`-only**; the app-scaffold path (no profile) emits nothing new.
- **OQ-scope → single-doc card browse only.** Cross-doc / corpus search is the index renderer's job (REQ-03 / REQ-06), explicitly a non-goal here.

---

## Overview

Add a **free-text search box** to the profiled navigator's requirement **card browse** (`#outline`).
As the reader types, cards whose structured text (key · name · statement · verify · Touches paths)
does not match the term are hidden in real time. Search **composes** with the two filters that already
exist — the PF-1 status chips and the paging group — so the visible set is always the intersection
`status ∧ search ∧ page`. The control is **definition-owned** (registered in the View Definition like
paging was) and **profiled-navigator-only**: with no `payload.profile` (the deterministic app-scaffold
preview) not one byte changes.

This is a small, high-leverage readability rung on the card browse: a long requirements doc (REQ-01…27
is already ~30 cards) is hard to scan; the tree renderer already lets a reader jump by typing, and this
brings the same affordance to the card browse by adapting the proven pattern rather than inventing one.

---

## Objectives

- **O-1** — A reader can narrow a long card browse to the requirements matching a typed term in real time (no reload, no server round-trip).
- **O-2** — Search **composes** with the status filter and paging: the visible set is the intersection, and clearing any one predicate restores the others' view.
- **O-3** — The search index is **structural** (typed `item.fields`/`item.touches` BY KEY), so what matches is exactly what the card is *about*, not incidental rendered chrome.
- **O-4** — The control is **definition-owned** (registered in `control.groups` + a region binding), inheriting the REQ-14 relabel/override cascade for free.
- **O-5** — **Byte-identity** of the app-scaffold path is preserved: the entire feature is gated on `payload.profile` / `body.nav-profiled`.

---

## Risks

| ID | Risk | Mitigation |
|----|------|------------|
| RK-1 | The new input/JS/blob leaks onto the app-scaffold path and breaks byte-identity | Everything is `payload.profile`-gated (input rendered only under profile; blob stamped only in the `if(payload.profile…)` branch of `renderItem`; CSS under `body.nav-profiled`; JS no-ops when the input element is absent) — guarded by `tests/unit/wireframe/test_render_profile.py::test_no_profile_is_byte_identical` (FR-7). |
| RK-2 | Search and paging/status don't intersect (paging pages hidden cards; counts lie) — a REAL pre-existing seam (`pagedCards()` `_template.py:1365-1368` ignores `pf-hidden`) | FR-5 makes `pagedCards()` return the **survivor set** (not `pf-hidden`, not `srch-hidden`); paging re-runs via `_pagingHook` after each search/status change so the page window and counts reflect the filtered set. |
| RK-3 | Over-matching / noisy results (a term matches long prose everywhere) | Blob is bounded to the discriminating typed fields (key/name/statement/verify/Touches paths), lowercased substring only — no fuzzy/regex/ranking (a non-goal), so matches are predictable and explainable. |
| RK-4 | The blob re-parses prose and drifts from what the card shows | Blob is built BY KEY from `item.fields`/`item.touches` in one function mirroring `render_tree.py:_search_blob` — the same structured source the card renders from, so index and display can't drift. |

---

## Profile: internal

Local render only; no network egress; no LLM; no new persisted data. The search index is derived
client-side from the `#plan-data` JSON already embedded in the page.

---

## Functional Requirements

- **FR-1 — Profiled-only search input.** When `payload.profile` is active, the control panel renders a single free-text search `<input id="q-cards">` (placeholder "search requirements…"), adapting the proven `id="q"` input from the tree renderer; the app-scaffold path (no profile) renders no such input. · **Name:** A profiled-only free-text search input renders in the navigator control panel and is absent on the app-scaffold path. · **Touches:** `code: src/startd8/wireframe_view/_template.py` (control-panel render, profile-gated) · `code: src/startd8/navigator/render_tree.py` (pattern source `:326-345`) · **Verify:** `render_html(_plan(), profile=<domain>)` contains `id="q-cards"`; `render_html(_plan())` (no profile) does not. · **Serves:** O-1
- **FR-2 — Structural per-card data-search blob.** Each requirement card carries a `data-search` attribute built structurally BY KEY from `item.key` + `item.fields.name/statement/verify` + `item.touches[].path` (lowercased, space-joined), stamped only inside `renderItem`'s `if(payload.profile…)` branch — never a re-parse of rendered prose. · **Name:** Each card carries a structural data-search blob built by key from its typed fields and Touches, never a prose reparse. · **Touches:** `code: src/startd8/wireframe_view/_template.py` (`renderItem` `:932-1001`, new blob builder mirroring `_search_blob`) · **Verify:** a profiled card's `data-search` for a known requirement contains its Verify text and a Touches path, all lowercase; a card with no matching field yields an empty-but-present blob. · **Serves:** O-3
- **FR-3 — Real-time substring filter.** Typing in the search input filters cards in real time on the `input` event: a card whose `data-search` does not `.includes()` the lowercased trimmed term gets a `srch-hidden` class (`display:none`); an empty term clears all `srch-hidden`. · **Name:** Typing filters the cards in real time by substring match, hiding non-matches and clearing on empty. · **Touches:** `code: src/startd8/wireframe_view/_template.py` (new `_applySearch`, `input` listener; CSS `.item.srch-hidden{display:none}` near `:508`) · **Verify:** setting the input to a term present in exactly one card's blob and dispatching `input` leaves exactly one card without `srch-hidden`; clearing the input removes every `srch-hidden`. · **Serves:** O-1
- **FR-4 — Intersect with the status filter.** Search intersects with the PF-1 status filter: a card is visible iff it is neither `pf-hidden` (status) nor `srch-hidden` (search); the two hide-classes are independent so toggling a status chip and typing a term compose without either clobbering the other's state. · **Name:** Search and the status filter compose as independent hide-classes so the visible set is their intersection. · **Touches:** `code: src/startd8/wireframe_view/_template.py` (`_applySearch` adds `srch-hidden` only; `_applyFilter` `:721-739` unchanged; section-emptiness recomputed against both) · **Verify:** with a status chip active AND a search term set, the visible cards equal the set that satisfies both predicates; clearing the term restores exactly the status-filtered set. · **Serves:** O-2
- **FR-5 — Page the survivor set (repairs status↔paging).** Paging pages the **survivor set** (cards that are not `pf-hidden` and not `srch-hidden`), and re-pages after every search/status change via `_pagingHook`; `pagedCards()` is narrowed to exclude the two filter hide-classes so the page window and the "showing X–Y of N" count reflect the filtered set. · **Name:** Paging pages the survivor set of both filters, repairing the pre-existing status-to-paging non-intersection. · **Touches:** `code: src/startd8/wireframe_view/_template.py` (`pagedCards` `:1365-1368`, `applyPaging` `:1369-1393`, `_pagingHook` `:1396`; invoke the hook from `_applySearch`/`_onChipClick`) · **Verify:** with page size 5 and a term matching 3 cards, the pager reads "showing 1–3 of 3" and no `pf-hidden`/`srch-hidden` card counts toward N. · **Serves:** O-2
- **FR-6 — Definition-owned search control.** The search control is registered in `BASE_NAVIG8R_DEFINITION.control.groups` as its own ordered group (mirroring how `paging` was added `:337-347`), and its input region is wired as a `regions.bindings` entry carrying a `data-scaffold` role (mirroring `detail`/`fullview` `:381-382`), so the REQ-14 `applyDefinitionOverride` relabel/override cascade applies to it for free and the base values render byte-identically. · **Name:** The search control is registered in the View Definition control groups and a region binding, inheriting the override cascade. · **Touches:** `code: src/startd8/navigator/view_definition.py` (`control.groups` `:312-348`, `regions.bindings` `:365-382`) · `code: src/startd8/wireframe_view/_template.py` (`applyDefinitionOverride` `:1107-1122` consumes the entry) · **Verify:** `to_render_profile(resolve(BASE_NAVIG8R_DEFINITION)).control["groups"]` contains a `search` group and `regions["bindings"]` a search region with a `scaffold` role; a domain delta relabeling the group's label appears in the rendered panel. · **Serves:** O-4
- **FR-7 — App-scaffold byte-identity.** The app-scaffold path stays byte-identical: with no profile the search input, `data-search` blob, `srch-hidden` CSS, and search JS emit nothing that changes the output; the `pagedCards()` narrowing (FR-5) is a no-op when no filter classes are ever applied. · **Name:** The app-scaffold path stays byte-identical because the whole feature is gated on payload profile. · **Touches:** `code: src/startd8/wireframe_view/_template.py` · `test: tests/unit/wireframe/test_render_profile.py` (`test_no_profile_is_byte_identical` `:34-36`) · **Verify:** `render_html(_plan()) == render_html(_plan(), profile=None)` remains green. · **Serves:** O-5

---

## Non-goals

- **NG-1** — No fuzzy matching, regex, tokenization, stemming, or relevance **ranking** — lowercased substring only (predictable + explainable; RK-3).
- **NG-2** — No cross-doc / corpus / multi-file search — that is the **index renderer's** job (REQ-03 a11y-renderer-and-corpus-index / REQ-06 corpus governance), which owns the corpus-level SOURCE×TOPOLOGY axis.
- **NG-3** — No server, network, or LLM involvement — the index is client-side over the already-embedded `#plan-data`.
- **NG-4** — No new persisted state (search term is ephemeral, not written to `localStorage` like sign-off is); no highlighting/marking of matched substrings within a card in v1.
- **NG-5** — No search over the tree/graph topologies here — the tree already has its own (`render_tree.py`); this is scoped to the card browse.

---

## Owned fields

The feature introduces no new NODE-SCHEMA fields — it **reads** existing structured fields
(`item.key`, `item.label`, `item.status`, `item.fields.{name,statement,verify}`, `item.touches[].path`).
It owns three runtime artifacts: the `q-cards` search input, the per-card `data-search` attribute, and
the `srch-hidden` visibility class; plus one definition entry (a `search` control group + region binding).

---

## Contract projection

- **Backend:** `python-cli-surface` — the profiled navigator HTML is emitted by `render_html` over `_template.py`; the definition is projected by `to_render_profile` over `view_definition.py`.
- **Vocabulary home:** the control taxonomy is DEFINITION-OWNED (`BASE_NAVIG8R_DEFINITION.control.groups` / `.regions.bindings`, `view_definition.py`) — the `search` group's labels/hint and the region's `data-scaffold` role live there, inheritable/overridable via the REQ-14 cascade.

| Entry | Where | Shape |
|-------|-------|-------|
| Search control (input) | `_template.py` control-panel render (profile-gated) | `<input id="q-cards">`, live `input` listener |
| `data-search` blob | `_template.py` `renderItem` (`if(payload.profile…)`) | lowercased space-joined string of `key`+`fields.{name,statement,verify}`+`touches[].path` |
| Filter JS | `_template.py` (`_applySearch` + `pagedCards` narrowing + `_pagingHook` re-run) | `srch-hidden` toggle; intersects `pf-hidden`; re-pages survivor set |
| View-Definition control entry | `view_definition.py` `control.groups["search"]` + `regions.bindings[<search-region>]` | ordered group + region binding with `data-scaffold` role |

---

## Embedded Iterations plan (acyclic)

| It | Deliverable | Depends on | Verify |
|----|-------------|------------|--------|
| **It-1** | Register the `search` control group + region binding in `BASE_NAVIG8R_DEFINITION` (base values ⇒ byte-identical) | — | FR-6 projection assertion; `test_no_profile_is_byte_identical` green |
| **It-2** | Structural `data-search` blob builder in `renderItem` (profile-gated), mirroring `_search_blob` | It-1 | FR-2 blob assertion |
| **It-3** | Profile-gated `q-cards` input + `_applySearch` live filter (`srch-hidden`) | It-2 | FR-1, FR-3 |
| **It-4** | Compose with status filter (independent hide-classes; section-emptiness over both) | It-3 | FR-4 |
| **It-5** | Narrow `pagedCards()` to the survivor set + re-run `_pagingHook` on search/status change | It-4 | FR-5 (paged count reflects filtered set; repairs the pre-existing status↔paging non-intersection) |
| **It-6** | Byte-identity guard sweep | It-1…It-5 | FR-7 |

Dependency edges It-1→It-2→It-3→It-4→It-5→It-6 form a chain (acyclic; no back-edges).

---

## Appendix A — Accepted (incoming review)

*(none yet — v0.2 initial)*

## Appendix B — Rejected (with rationale)

*(none yet)*

## Appendix C — Incoming (review rounds)

*(awaiting CRP R1)*
