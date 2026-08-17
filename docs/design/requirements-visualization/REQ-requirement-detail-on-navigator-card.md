# Requirement Detail on the Navigator Card — Requirements

**Project:** startd8-sdk   **Criticality:** medium
**Version:** 0.3 (design pivot — inline-only → inline peek + full-page route)   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan embedded below — Iterations; delivered via the Spec Delivery Loop)*
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · SOTTO_DESIGN_PRINCIPLE · the node-fields distillation (commit `1cd422bf` — reads the structured `WireframeItem.fields` this depends on) · REQ-view-definition-mode-and-control-consolidation (the View Definition that owns the region taxonomy this registers into)
**Audience:** operator / SDK contributors / requirement reader
**Trust boundary:** local render only; no network; no LLM
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-requirement-detail-card`
> **Semantic name:** *A navigator requirement card expands in place, on click, into a read-only detail PEEK (the promoted inspector) showing the requirement's full structured record — including the complete authored Touches list with a source-bound derived kind per entry — and the peek links (top and bottom) to a full-page single-requirement VIEW reached as a client-side `#<key>` route (deep-linkable, back to browse); all read structurally, registered as regions in the View Definition, profiled-navigator-only, app path byte-identical.*
> **Planned canonical ref:** `cc:intent:navig8r:requirement:detail-on-card`

## 0. Planning Insights (Self-Reflective Update)

> Planning against the shipped tree revealed the "full typed Touches" assumption is only half-true,
> and that the carry mechanism must honor the distillation just landed (`1cd422bf`).

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The node carries a full **typed** Touches list | `fr["touches"]` (via `parse_fr_lines_prefer_kit`) is a list of **raw path strings**, untyped; `attrs["touches"]` stores them comma-joined; only a code/test heuristic exists (`_lives_from_touches`, existence-gated) | Entry **kind** must be **derived** deterministically from the path (source-bound, not authored) — FR-4 adds `_typed_touches` |
| The detail panel is new UI | An inspector already renders every field (`buildInspect` → `.node-inspect`), but is **debug-gated** + styled as an edit grid | **Reuse/promote** it (FR-2), don't build a second panel — the anti-accidental-complexity directive |
| The typed list can ride in `fields` | `WireframeItem.fields` is `str→str`; encoding a **list** as a string + reparsing is the exact anti-pattern the distillation removed | Carry the typed list **structurally** as a first-class `touches` slot (FR-5), like `lives`/`was` |
| Card click is free | No card-level click handler exists in the profiled render today | FR-1 adds a profiled-only click toggle; app path keeps none (byte-identity) |
| The card-level click handler is simple | Every card is nested inside a `<details class="sec">` section wrapper, so a naive `closest("details")` bail matched that ancestor and swallowed **every** click | FR-1: the interactive-bail must be scoped to elements INSIDE the card (`w.contains(hit)`), not ancestors — a live regression the guard test now pins |
| Inline expand is the whole feature | Review of the inline peek showed a reader wants a **dedicated full page** per requirement, not just an in-list expand | Pivot (v0.3): keep the peek, add a **full-page client-side route** (FR-7) with `#<key>` deep-linking; the peek links to it (top+bottom) |
| The new surfaces are renderer-internal | The View Definition is the SSOT map of the renderer's anatomy (`regions.bindings`); leaving the band/detail/full-view unregistered makes the frame mode's map dishonest | FR-8: register `docband`/`detail`/`fullview` as region bindings + wire their `data-scaffold` roles |

**Resolved open questions:**
- **OQ-1 → Inline PEEK + full-page ROUTE (both), not side panel/modal.** The peek is the quick look; a full-page client-side route (same HTML file, `#<key>` deep-link) is the dedicated per-requirement page. No modal, no separate output file.
- **OQ-2 → Reader is read-only.** The contenteditable/not-displayed edit affordance stays behind the debug toggle (NR-4).
- **OQ-3 → Full-view link rides top AND bottom of the peek.** So a reader reaches the full page immediately on expand or after reading — never has to hunt for it.

## Overview

The navigator browse view was enriched (card signal strip, doc-context masthead band) but never gained
a **single-requirement detail view**: a reader cannot open one FR and see its complete record. The
closest thing — the debug inspector — already renders every field but is gated behind the debug toggle
and styled for QA/edit, not reading. This feature **promotes that inspector** into a read-only detail
panel that expands **in place** when a reader clicks a requirement card, showing the full structured
record (statement · verify · serves+objective · archetype · depends · won't · ships-when · evidence +
confidence · handle) **and the complete authored Touches list with a derived kind per entry**. All of it
reads the structured `WireframeItem.fields` (from the just-landed distillation) plus first-class slots —
no prose re-parse — and rides the profiled-navigator path only, so the app scaffold render stays
byte-identical.

## Objectives

- **O-1:** A reader can open one requirement and see its **entire** record — as a quick inline peek AND
  as a dedicated full page — reachable from the browse and directly linkable (`#<key>`).
- **O-2:** Reuse the existing inspector machinery + the payload the distillation already produces — add
  **no** second rendering/projection path, no separate output file, and **one** shared field extraction.
- **O-3:** Surface the full authored **Touches** blast-radius (every entry), each tagged with a
  source-bound kind, so a reader sees *what a requirement touches and of what nature*.
- **O-4:** Preserve app-path byte-identity and the distillation's structured-not-stringly discipline.
- **O-5:** Keep the View Definition an honest map of the renderer — register the new regions there.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Promoting the inspector changes the app-scaffold card | FR-6: click handler + panel are profiled-only (`payload.profile` gated); app path unchanged; assert byte-identity unedited | high |
| scope | Deriving Touches kinds "invents" typing not in the source | FR-4: the kind is a **deterministic function of the authored path** (extension/tree), source-bound — never guessed from meaning | high |
| quality | Re-introducing a stringly list encode (the cruft just removed) | FR-5: `touches` is a first-class structured slot (typed pairs → JSON array), omit-when-empty; no client regex | high |
| scope | Click-to-expand collides with the existing "show a sketch" / inspect toggles | FR-1: toggle is idempotent and scoped to the card body; coexists with the debug inspectCells path (NR-4) | medium |
| reliability | The card-level click bails on an ANCESTOR match (the `<details class="sec">` wrapper), swallowing every click | FR-1: bail only when the interactive element is INSIDE the card (`w.contains(hit)`); a guard test pins this exact regression | high |
| scope | The full-page route drifts from the peek (two field renderers) | FR-3: one shared `recordEntries`/`touchesRows` extraction feeds both views — no second field-mapping to drift | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Click-to-expand PEEK, with top+bottom full-view links.** A profiled requirement card is clickable and toggles an inline read-only detail peek directly beneath its summary; the peek carries an `open full view →` link at **both** its top and its bottom (OQ-3). The card-level click ignores only interactive elements **inside** the card (`w.contains(hit)`), never the `<details class="sec">` section wrapper that is an ancestor of every card. Touches: `src/startd8/wireframe_view/_template.py`. Verify: a profiled render wires a card click handler guarded by `w.contains(hit)` that toggles a `.ci-detail` panel containing two `.cd-full` links; the app path (no profile) wires no such handler (grep the emitted JS).
- **FR-2 — Promote the inspector (reuse, don't rebuild).** The peek reuses the card's stashed `_nodeData` + append lifecycle (the inspector machinery), rendered read-only; the debug edit-grid (`buildInspect`) stays behind the `inspectCells` toggle. Touches: `src/startd8/wireframe_view/_template.py`. Verify: clicking a card with the debug toggle OFF renders the read-only peek; the contenteditable edit cells appear only under the debug toggle.
- **FR-3 — Full structured record (shared extraction).** Both the peek and the full-page view show the requirement's complete record — name, statement, verify, serves + objective, type (archetype + gloss), depends-on, won't, ships-when, evidence (`lives`) + confidence, handle — from **one** shared extraction (`recordEntries` + `touchesRows`) read structurally from `item.fields` + first-class slots (no prose re-parse, no duplicated field logic to drift). Touches: `src/startd8/wireframe_view/_template.py`. Verify: a node carrying every field yields one labelled row per present field in **both** views; absent fields render nothing.
- **FR-4 — Full typed Touches list.** Both views list **every** authored Touches entry with a kind derived deterministically from its path — `test` (tests/ tree or `test_`/`_test`), `code` (source extension), `config` (`.yaml`/`.toml`/`.json`/`.ini`/`.env`), `doc` (`.md`/`.rst`/`.txt`), `build` (Dockerfile/`.mk`/lockfiles), else `other`/non-path — source-bound, never inferred from meaning. Touches: `src/startd8/navigator/project.py` (`_classify_touch`/`_typed_touches` — the projector, not the source; see §0). Verify: an FR whose Touches names `x.py`, `tests/test_x.py`, and `app.yaml` yields three entries kinded `code`, `test`, `config`.
- **FR-5 — Structured carry (no re-stringification).** The typed Touches list travels as a first-class structured `WireframeItem.touches` slot (ordered `(path, kind)` pairs → JSON array of `{path, kind}`), omit-when-empty; the client reads it structurally with no regex/blob parse. Touches: `src/startd8/wireframe/plan.py`, `src/startd8/wireframe_view/compose.py`, `src/startd8/navigator/project.py`. Verify: the payload carries a `touches` array of objects; no client-side split/regex reconstructs it.
- **FR-6 — Byte-identity (profiled-navigator-only).** The click handler, both panels, the `#fullview` route, and the `fields`/`touches` payload keys are emitted/active only under a domain profile (`resolveHash` early-returns when `!payload.profile`); the app scaffold path (no profile) is byte-identical. Touches: `src/startd8/wireframe_view/compose.py`, `src/startd8/wireframe_view/_template.py`. Verify: `render_html(_plan()) == render_html(_plan(), profile=None)` stays green, unedited.
- **FR-7 — Full-page requirement view (client-side route + deep-link).** An `open full view →` link (or a `#<key>` URL) opens a dedicated full page for **one** requirement (`buildFullView`): it hides the whole browse (`body.fullview-open` → `.wrap`/`#debug` hidden, `#fullview` shown), renders the shared record + typed Touches in a fuller layout with a large serif name heading + FR-key + status, and a `← all requirements` back link that clears the hash and restores the browse. The route resolves on `hashchange` **and** after each `renderAll` (deep-link on load). No separate output file, no new renderer. Touches: `src/startd8/wireframe_view/_template.py`. Verify: setting `location.hash = "#<key>"` adds `body.fullview-open` and renders one `.fv` page for that key; an empty/unknown hash removes it; loading the file at `#<key>` opens that page directly.
- **FR-8 — Register the new surfaces in the View Definition.** The doc-context band, the inline detail peek, and the full-page view are registered as region bindings (`docband`/`detail`/`fullview`) in `BASE_NAVIG8R_DEFINITION.regions.bindings`, and their rendered elements carry the matching `data-layer`/`data-scaffold` roles, so the scaffold/frame mode maps the renderer's anatomy honestly (NR-1: the definition declares WHAT regions exist; the renderer owns the interaction). Touches: `src/startd8/navigator/view_definition.py`, `src/startd8/wireframe_view/_template.py`. Verify: `BASE_NAVIG8R_DEFINITION.regions["bindings"]` contains `docband`, `detail`, `fullview`; the emitted `#fullview`/`dc-band`/`ci-detail` elements carry a `data-scaffold` role; the golden-profile tests (which derive `_BASE_REGIONS` from the base) stay green.

## Non-goals

- **NR-1 — No authored/per-backend rich Touches typing.** Kinds are path-derived buckets only; explicit authored entry-kinds (e.g. `cli-command`, `route`) are deferred.
- **NR-2 — No modal / no separate output file.** The full-page view is a **client-side route within the same single HTML file** (a `body.fullview-open` takeover), not a modal overlay and not a per-requirement file on disk. (v0.2's "inline only" is superseded — see §0.)
- **NR-3 — No new renderer / output format.** No `--renderer detail`; both the peek and the full page ride the existing `render_html` path and the payload the distillation already produces.
- **NR-4 — Reader detail is read-only.** The contenteditable + not-displayed edit affordance stays debug-gated; this feature does not add editing.

## Owned fields

Only humans enter: the requirement's authored det-req content (Touches, Verify, Serves, etc.). This
feature derives kinds and renders; it authors nothing.

## Contract projection

- **Backend:** python-cli-surface (the navigator render surface + its HTML template).
- **Vocabulary home (cite):** NODE-SCHEMA (node fields) · `WireframeItem` (the render contract) ·
  REQ-distill-node-fields-contract (the structured `fields`/`_node_fields` seam this builds on).

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| card click → peek toggle | interaction (JS) | `renderItem` click handler (`w.contains(hit)`-guarded); `.ci-detail` | profiled-only (FR-1/6) |
| `recordEntries` / `touchesRows` | render (JS) | one shared extraction → both peek + full page | no drift (FR-3) |
| `buildDetail` (peek) | render (JS) | reader panel; `open full view →` top+bottom | reuse `_nodeData` (FR-1/2) |
| `buildFullView` + `resolveHash` | route (JS) | `#<key>` client route; `body.fullview-open` takeover; back link | FR-7 |
| `_classify_touch` / `_typed_touches` | derivation (py) | `[(path, kind)]`, path→kind deterministic | source-bound, in `project.py` (FR-4) |
| `WireframeItem.touches` | contract (py) | `Tuple[Tuple[str,str],...]`, omit-when-empty | structured carry (FR-5) |
| `regions.bindings` `docband`/`detail`/`fullview` | definition (py) | region map + `data-scaffold` roles | View Definition SSOT (FR-8) |

## Iterations (embedded plan)

1. **Data** — `_classify_touch`/`_typed_touches` in `project.py`; `WireframeItem.touches` slot in `plan.py`;
   populate in `project.py`; emit omit-when-empty in `compose.py`. (FR-4, FR-5) — acyclic root.
2. **Promote (peek)** — `buildDetail` reader panel over the shared `recordEntries`/`touchesRows`; render the
   full record + typed Touches; top+bottom full-view links. (FR-2, FR-3) — depends on 1.
3. **Trigger** — profiled-only card click toggling the peek, guarded by `w.contains(hit)` (ancestor-safe);
   coexist with debug/sketch toggles. (FR-1) — depends on 2.
4. **Full page** — `buildFullView` + `resolveHash`/`hashchange`; `#fullview` container + `body.fullview-open`
   CSS; deep-link on load. (FR-7) — depends on 1–2.
5. **Register** — `docband`/`detail`/`fullview` bindings in `view_definition.py` + `data-scaffold` roles on
   the elements. (FR-8) — depends on 4.
6. **Guard** — byte-identity + tests (kind derivation, structured carry, profiled-only, the `w.contains`
   ancestor-safety regression pin, bindings present). (FR-6) — depends on 1–5.

## Appendix A — Accepted (with where merged)
- **Full-page view as a client-side route (v0.3 pivot)** — accepted into FR-7: a dedicated per-requirement page reached from the peek, within the same HTML file, `#<key>` deep-linkable. Supersedes v0.2's inline-only stance without adding a separate renderer/file.
- **Full-view link at top AND bottom of the peek (OQ-3)** — accepted into FR-1.
- **Register the new regions in the View Definition** — accepted into FR-8.

## Appendix B — Rejected (with rationale)
- **Separate `--renderer detail` output / a file per requirement** — rejected (NR-3): duplicates projection + chrome; a third rendering path + N files is the accidental complexity this initiative is actively removing. The full page is a client-side route instead.
- **Modal / side panel** — rejected (NR-2): more chrome + state; a full-page takeover (`body.fullview-open`) reuses the card data and gives a cleaner reading page.
- **Encode typed Touches into `fields` as a string** — rejected (FR-5): re-introduces the prose-blob reparse the distillation (`1cd422bf`) just deleted.
- **Two field renderers (peek vs full page)** — rejected (FR-3): collapsed to one shared `recordEntries`/`touchesRows` extraction to prevent mirror drift.

## Appendix C — Incoming review rounds
*(awaiting CRP)*

---

*v0.3 — Design pivot: inline-only → inline peek + full-page client-side route (`#<key>` deep-link), with
the full-view link top+bottom (OQ-3), one shared field extraction (no drift), the ancestor-safe click
guard (a live regression), and the new regions registered in the View Definition (FR-8). Builds on the
node-fields distillation (`1cd422bf`) + the doc-context band. Foundation shipped; guard tests pending.*
