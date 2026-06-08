# Confirm Affordance — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-08
**Status:** Plan (post-exploration)
**Requirements:** `CONFIRM_AFFORDANCE_REQUIREMENTS.md` (v0.2)

---

## Discoveries (planning pass over the v0.1 requirements)

| v0.1 Assumption | Planning Discovery |
|---|---|
| Confirm can reuse delete's row-swap mechanic | **Delete's swap returns a throwaway flash *placeholder* row** (`<tr><td colspan=N><p class="flash">…deleted.</p>`), not a real row. Confirm's row must **persist with an updated control**, so it CANNOT reuse that — it must return a real, re-rendered `<tr>` whose confirm button + `confirmed` cell reflect the new state. |
| Row markup is a single source of truth | It is **not.** The full row lives only inside `render_list_template`'s `{% for %}` loop; the delete/confirm swap fragments are built **separately**. To re-render a row from the confirm route without duplicating markup, the row body must be extracted into a shared **`<e>/_row.html` partial** (new schema-only artifact, kind `htmx-row`) that both the list loop (`{% include %}`) and the confirm route (`TemplateResponse(".../_row.html", {"item": obj})`) use. This is the OQ-4 fork, resolved toward "shared partial." |
| FR-CA-6 "no new artifact kind" | False if we extract the partial — there IS a new per-entity template (`htmx-row`), but it is **schema-only / 1-hash** (no manifest), so `web.py`/list stay schema-derived and no 2-hash machinery is needed. FR-CA-6 corrected to "no new *2-hash* kind; one new schema-only template kind." |
| FR-CA-8: route-smoke covers the confirm POST | **Route-smoke is GET-only by construction** (`_get_paths()` filters `"GET" in r.methods`) — exercising a POST is a *new capability* for that suite, not a case. AR-5 itself said GET-smoke can't see actions. Narrow FR-CA-8 to **existence**: assert `POST /ui/<e>/{id}/confirm` is a registered `APIRoute` (cheap, catches "the action vanished"); behavioral toggling stays in the SDK runtime smoke (FR-CA-7). |
| OQ-1 one-way vs toggle | `obj.confirmed = not obj.confirmed` — full toggle is the **same handler, zero extra cost**. Resolve to full toggle. |
| OQ-5 predicate | `confirmed` scalar of type `Boolean` is the exact, sound predicate (it already implies `_PROVENANCE_OMIT` membership for the strtd8 contract; coupling to `_PROVENANCE_OMIT` adds nothing). A non-provenance `confirmed: Boolean` legitimately gets a toggle too. |
| OQ-6 durability vs transient flash | The list **already renders `confirmed`/`source` as read-only columns** (`_form_fields` = all scalar fields). Re-rendering the row updates that cell, so confirmed state is **durably visible for free**; the swap's micro-flash is just immediate feedback. No badge column needed. |
| OQ-2 detail parity | Detail has no rows; a toggle there needs its own fragment target. **List-first**, detail deferred — narrows v1. |
| OQ-3 hx-confirm guard | Confirm is reversible → **no dialog** (delete keeps its destructive guard). |

## Step plan

1. **Detection helper (FR-CA-1)** — `htmx_generator.py`: `_confirm_field(schema, name)` → the
   `confirmed` field iff it's a `Boolean` scalar AND the entity has a single-column PK; else None.
2. **Row partial (OQ-4 / FR-CA-3/4)** — extract the per-row `<tr>…</tr>` body from
   `render_list_template` into `render_row_template` → `app/templates/<e>/_row.html`
   (kind `htmx-row`, entity-tagged, schema-only header). The list loop becomes
   `{% for item in items %}{% include "<e>/_row.html" %}{% endfor %}`. The partial renders the
   cells + view/edit/delete + (when `_confirm_field`) the confirm control. Row keeps `id="row-{pk}"`.
   - Confirm control: unconfirmed → `<button hx-post=".../confirm" hx-target="#row-{rid}"
     hx-swap="outerHTML">Confirm</button>`; confirmed → a `✓` marker + an **Unconfirm** button
     (same POST). Label/branch via `{% if item.confirmed %}`.
3. **Confirm route (FR-CA-2)** — `_entity_routes`: when `_confirm_field`, emit
   `POST /ui/<e>/{id}/confirm` → load (404 if absent), `obj.confirmed = not obj.confirmed`,
   commit, refresh, `TemplateResponse(request, "<e>/_row.html", {"item": obj})`. Returns the
   re-rendered row (FR-CA-4) — the swap leaves a working, restated control.
4. **render_ui wiring** — emit `<e>/_row.html` for every entity (uniform; the include is
   unconditional, the confirm control inside is the conditional). Drift `_renderers` gains
   `htmx-row` → `render_row_template` (schema-only path, alongside `htmx-list`).
5. **Tests (FR-CA-7/8)** — `test_htmx.py`: confirm route emitted only for `confirmed`+PK entities;
   absent otherwise; row partial carries the control with correct initial branch; list `{% include %}`s
   the partial. `test_runtime_smoke.py`: POST confirm flips the served row's `confirmed`, the
   returned fragment shows the new state + control flip, second POST flips back. Route-smoke
   emitter (`test_emitter.py`): assert the confirm route is **registered** for confirmed-bearing
   entities (existence floor, FR-CA-8).
6. **Drift/round-trip sanity + commit** — `--check` in-sync with the new partial; full
   backend_codegen + wireframe suites green; the wireframe `claimed_paths` cross-check learns the
   new `_row.html` path (FR-W14 golden mirror — verify the wireframe plan emits it, else the
   cross-check test fails).

**Risk flagged by the plan:** step 2 touches `render_list_template`, whose exact byte output is
asserted in `test_htmx.py` and mirrored by the wireframe golden cross-check. Extracting the partial
changes the list template's bytes (now an `{% include %}`) and adds a path — both the list
byte-assertions and `wireframe/plan.py` `_entities`/forms path lists must move in lockstep
(the `test_cross_check.py` gate exists precisely for this).

**Not in plan (confirmed out):** bulk confirm, confirm-on-create, `source` mutation, detail-page
toggle (v1), generic boolean toggles, POST *behavior* in route-smoke (existence only).
