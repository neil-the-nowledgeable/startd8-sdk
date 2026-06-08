# Confirm Affordance (CRUD-Archetype `confirmed` Toggle) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update; pre-CRP)
**Date:** 2026-06-08
**Status:** Implemented (v1; FR-CA-5 detail toggle deferred to v1.1)
**Plan:** `CONFIRM_AFFORDANCE_PLAN.md`
**Companion:** `FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md` (the sibling that opened the "deterministic
UX defaults" category — this is instance #2), `PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (the
shipped CRUD archetype this amends), `src/startd8/backend_codegen/htmx_generator.py` (the generator
being changed). Motivating gap: **strtd8 AR-5** (filed 2026-06-07, "found by real use",
`strtd8/docs/kickoff/VALIDATION_AND_MANIFEST_DERIVATION.md` §7) — the generated CRUD UI has **no
way to set `confirmed`**, so the suggest→confirm loop (their O-2, "nothing counts until the user
confirms it") has no button. Explicitly scoped by the consumer as **SDK work, not app glue**.

> **Objective.** The deterministic CRUD archetype emits a **confirm toggle** for any entity whose
> contract carries the `confirmed` provenance Boolean: an HTMX `POST /ui/<entity>/{id}/confirm`
> that flips `confirmed`, row-swaps in place (like delete) with a `✓ {Entity} confirmed.` flash,
> and is shown on the list (and detail). **Schema-auto-detected** (the `confirmed` field's presence
> is the trigger) — no new manifest, no per-entity config. All `$0` LLM, byte-identical,
> drift-checked.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 (post-planning). The planning pass
> (`CONFIRM_AFFORDANCE_PLAN.md` §Discoveries) revealed 4 corrections + resolved all 6 OQs:

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| Confirm reuses delete's row-swap | Delete's swap returns a **throwaway flash placeholder row**, not a real row; confirm needs the row to **persist with an updated control** | FR-CA-3/4: confirm must return a **re-rendered real `<tr>`**, not a flash fragment |
| Row markup is one source of truth | It is **not** — the row body lives only in `render_list_template`'s loop; swaps are built separately | New **`<e>/_row.html` partial** (kind `htmx-row`, schema-only) shared by the list `{% include %}` and the confirm route; resolves OQ-4 |
| FR-CA-6 "no new artifact kind" | The partial **is** a new artifact, but schema-only / 1-hash | FR-CA-6 corrected: no new *2-hash* kind; one new schema-only template kind |
| FR-CA-8: route-smoke exercises the confirm POST | Route-smoke is **GET-only by construction**; exercising POST is a new capability for that suite (and AR-5 said GET-smoke can't see actions) | FR-CA-8 narrowed to **existence** — assert the confirm route is *registered*; behavior stays in the SDK runtime smoke (FR-CA-7) |

**Resolved open questions:**
- **OQ-1 → full toggle.** `obj.confirmed = not obj.confirmed` is the same handler at zero extra
  cost; one-way confirm would trap mis-clicks with no UI escape.
- **OQ-2 → list-first, detail deferred.** Detail has no rows; its toggle needs a separate fragment
  target — a clean v1.1 follow-up, not v1 (FR-CA-5 marked deferred).
- **OQ-3 → no guard dialog.** Confirm is reversible; an `hx-confirm` prompt is pure friction.
  Delete keeps its destructive guard.
- **OQ-4 → shared `_row.html` partial.** Both the list loop and the confirm-swap render the row
  through one template — no duplicated markup, no drift between list rows and swapped rows.
- **OQ-5 → predicate is `confirmed: Boolean` scalar + single-column PK.** No `_PROVENANCE_OMIT`
  coupling (adds nothing); a non-provenance `confirmed` Boolean legitimately gets a toggle.
- **OQ-6 → column provides durability; flash is transient.** The list already renders
  `confirmed`/`source` as read-only columns; the re-rendered row updates that cell, so confirmed
  state is durably visible for free — no badge column needed.

---

## 1. Problem Statement

`backend_codegen` omits `confirmed` from writable form fields on purpose: `confirmed` is in
`ai_layer._PROVENANCE_OMIT = {"source", "confirmed", "ownerId", "createdAt", "updatedAt"}`, so the
create/edit form never asks a user to hand-type it (FR-PG-5). That decision is correct — but it
left **no other way to set it**. The result is the AR-5 gap: AI suggestions are written with
`source:"ai", confirmed:false`, and the UI can *create* and *delete* them but never **accept** one.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Edit/create form | `confirmed` omitted (FR-PG-5) | Correct — but no compensating control |
| Detail page | `confirmed` shown read-only | Display only; can't toggle |
| List page | row + view/edit/delete actions | No confirm action |
| Only "confirm" in templates | `hx-confirm="Delete?"` dialog | Unrelated — it's a JS confirm prompt, not the domain verb |
| Route-smoke | GET-only floor | Proves a page renders, **not** that an action exists — missed AR-5 |

This is the **curation half** of the provenance design: the generator already writes
`source`/`confirmed`, displays them (FR-12 on the consumer side), and omits them from forms — but
the *transition* `confirmed: false → true` has no deterministic affordance. It is also the **second
instance** of the category `FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md` §1 named: *deterministic UX
defaults — behavior decisions the generator must make uniformly.* The first (post-submit
redirect/flash) shipped; this is the next.

## 2. Requirements

**FR-CA-1 (auto-detection, no manifest).** The confirm toggle is emitted for an entity **iff** its
contract declares a scalar field named `confirmed` of type `Boolean` with a single-column PK
(needs a by-id route). Presence is the only trigger — no `views.yaml`/`forms:` entry, no opt-in.
Entities without `confirmed` are unchanged.

**FR-CA-2 (the toggle route).** Emit `POST /ui/<entity>/{id}/confirm` that loads the row, flips
`confirmed` (true→false→true — idempotent per click, not one-way), commits, and returns an HTMX
fragment. 404 when the row is absent, matching the existing detail/edit/delete handlers.

**FR-CA-3 (list affordance + shared row partial).** The per-row `<tr>` is rendered through a new
**`app/templates/<e>/_row.html`** partial (kind `htmx-row`, entity-tagged, schema-only) that the
list loop `{% include %}`s and the confirm route re-renders. The row gains a confirm control next
to view/edit/delete; clicking it `hx-post`s to the confirm route with `hx-target="#row-{pk}"` and
`hx-swap="outerHTML"`. The confirm route returns the **re-rendered real row** (not a flash
placeholder — that is delete's mechanic; confirm's row must persist), so the swapped-in row keeps a
working, restated control and an updated `confirmed` cell. One row template, no duplicated markup.

**FR-CA-4 (control reflects state).** The control branches on `item.confirmed`: unconfirmed →
**Confirm**; confirmed → a `✓` marker + an **Unconfirm** affordance (same POST — full toggle). The
re-rendered row after the swap shows the flipped control automatically (it is the same partial).

**FR-CA-5 (detail parity — deferred to v1.1).** The detail page toggle is **out of v1** (OQ-2):
detail has no rows, so it needs its own fragment target — a clean follow-up, not a blocker for the
list affordance that closes AR-5.

**FR-CA-6 (drift).** `web.py` and the list template re-render byte-identically; the new `_row.html`
partial is **schema-only (1-hash)** — no manifest, no 2-hash machinery (unlike the `forms:`-driven
post-submit work). The list template's bytes change (it now `{% include %}`s the partial) and one
new path appears, so the list byte-assertions and the wireframe golden cross-check
(`test_cross_check.py`) move in lockstep with the generator.

**FR-CA-7 (tests).** Unit: route emitted only for `confirmed`-bearing entities; toggle flips both
directions; list control present + correct initial state; absent for non-`confirmed` entities and
PK-less entities. Runtime smoke: POST confirm on a real served row flips the DB value and the
swapped fragment shows the new state; a second POST flips it back.

**FR-CA-8 (route-smoke existence floor).** The generated route-smoke suite is **GET-only by
construction** (it can't exercise a POST), which is exactly why it *missed* AR-5. It therefore
asserts the confirm route is **registered** (`POST /ui/<e>/{id}/confirm` present in `app.routes`)
for every `confirmed`-bearing entity — catching "the action vanished" at the generated-app level.
Behavioral toggling is covered by the SDK runtime smoke (FR-CA-7), not here.

## 3. Non-Requirements

- **No new manifest / no per-entity config** — schema presence is the whole trigger (contrast the
  `forms:` knob, which genuinely varies per entity; "is this row confirmed" does not).
- **No bulk confirm / no confirm-all** — one row, one click.
- **No confirm on create** — creation defaults `confirmed:false` (provenance design); accepting is
  always a separate, explicit act.
- **No generalization to arbitrary Boolean toggles** — this is specifically the `confirmed`
  provenance verb, not a generic "toggle any bool" feature (that would be a different, manifest-
  driven increment).
- **No cross-entity cascade** (confirming a parent does not confirm children).
- **No `source` mutation** — confirming does not rewrite `source` from `ai` to `human`; provenance
  of *origin* is immutable, only the *acceptance* flag moves (matches the consumer's design where
  editing an AI item preserves its origin marker, FR-12).

## 4. Open Questions

All six v0.1 open questions were resolved by the planning pass — see §0. None remain for v1.
One scope item was explicitly **deferred to v1.1**: the detail-page toggle (FR-CA-5 / OQ-2).

---

*v0.2 — Post-planning self-reflective update. 4 requirements corrected (FR-CA-3/4/6/8), 1 deferred
(FR-CA-5 → v1.1), 6 open questions resolved. The load-bearing discovery: confirm cannot reuse
delete's throwaway flash-row swap — it needs a re-rendered real row, which forces a shared
`<e>/_row.html` partial (the row-markup single-source the list never had). Grounded against
`htmx_generator.py` (delete swap + list loop), `test_emitter.py` (GET-only route-smoke), and the
`confirmed`-field detection verified on a strtd8-like contract.*
