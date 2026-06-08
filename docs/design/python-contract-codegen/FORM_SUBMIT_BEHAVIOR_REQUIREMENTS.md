# Form Post-Submit Behavior (Create-Record Defaults) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update; pre-CRP)
**Date:** 2026-06-07
**Status:** Implemented (FR-1..10 + OQ-3/OQ-4 gate-half + polish; 2026-06-07). One written item
unbuilt — deriving `on_create` from prose (OQ-4 derivation half) remains future work.
**Plan:** `FORM_SUBMIT_BEHAVIOR_PLAN.md`
**Companion:** `PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (the shipped single-entity generator this
amends), `VIEW_GENERATOR_REQUIREMENTS.md` (the `views.yaml` manifest this proposes to extend),
`src/startd8/backend_codegen/htmx_generator.py` (the generator being changed). Motivating defect:
the generated create/update handlers answer a **plain browser form POST** with an
`HX-Redirect` header the browser ignores — the user submits a form and lands on a **blank page**.

> **Objective.** Define the deterministic default for *what happens after a user submits a
> create-record form* in generated apps: a **Post/Redirect/Get (303)** to the **new record's detail
> page** carrying a stateless **`?created=1` query-param flash** that renders a "✓ {Entity}
> stored." confirmation banner — configurable per entity via an `on_create` manifest field
> (`detail | list | form | confirmation`). All `$0` LLM, byte-identical, drift-checked, no session
> state.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 (post-planning). The planning pass
> (`FORM_SUBMIT_BEHAVIOR_PLAN.md` §Discoveries) revealed 5 corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| `on_create` is a per-view-ish field "in views.yaml" | `views.yaml` is the class-3 composite-view manifest, but `parse_views()` ignores unknown **top-level** keys | FR-4: home is a new **top-level `forms:` section** in `views.yaml` — disjoint sections, two strict parsers, non-breaking for `view_codegen`/wireframe |
| A views.yaml could carry form config alone | `parse_views()` raises on zero views | FR-4: the backend-side `forms:` parser tolerates a missing/empty `views:` list |
| `session.refresh(obj)` needed for the PK | `cuid()`/`uuid()` PKs are Python-side `default_factory` (pre-commit); int-autoincrement is DB-side | FR-2: `commit(); refresh(obj)` kept — covers both uniformly |
| Banner needs manifest-aware template variants | Banner blocks are **unconditional** Jinja; routes always pass the query param; only `web.py` routing + the artifact *set* vary | FR-3/FR-7 simplified: template kinds stay 1-hash schema-only; only `fastapi-web-forms` + `htmx-created` are 2-hash |
| FR-8 fallback "logged in the generation report" | No generation report exists; pk-presence is known at generation time | FR-8: deterministic gen-time fallback + emitted code comment |

**Resolved open questions:**
- **OQ-1 → top-level `forms:` in `views.yaml`** (mechanism above). Keeps "declared UI behavior"
  in one manifest, per the kickoff decision, without touching the view-archetype vocabulary.
- **OQ-2 → backend owns the parse.** New `backend_codegen/forms_manifest.py`;
  `render_ui()`/`assemble()` grow `forms_text`/`views_text`; CLI: `generate backend --views`.
- **OQ-3 → deferred.** Wireframe surfacing of `on_create` is not v1.
- **OQ-4 → deferred.** `forms:` is optional with full defaults; extraction round-trip learns it
  when kickoff ingestion starts deriving it.
- **OQ-5 → inline blocks.** No shared `_flash.html` partial — keeps the template set flat and
  the per-entity kinds 1-hash.
- **OQ-6 → banner only in v1.** `list`/`form` destinations still carry `?created={pk}` so
  row-highlight/link can be added without changing redirect contracts.

---

## 1. Problem Statement

`backend_codegen` derives the entity HTMX UI (list/detail/form) purely from `schema.prisma`. The
form is a plain `<form method="post">` (`htmx_generator.py:307`) — no `hx-post`, no `hx-boost` on
the base layout. But the create and update handlers respond with
`HTMLResponse(headers={"HX-Redirect": "/ui/{e}"})` (`htmx_generator.py:416`, `:458`).
`HX-Redirect` is only honored by HTMX-initiated requests; a plain browser POST ignores the header.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Create handler (`create_{e}`) | empty 200 + `HX-Redirect` header | Browser shows a **blank page** after submit; no PRG, refresh re-POSTs |
| Update handler (`update_{e}`) | same pattern | Same blank page after edit |
| Confirmation message | none anywhere | User gets no signal the record was stored |
| Post-submit destination | implied list page (unreachable via the dead header) | Not a designed decision; not configurable |
| Session/flash infra | none (deliberate — stateless `$0` skeleton) | Any confirmation mechanism must be stateless |
| Delete (row button) | `hx-post` + row swap | Works (HTMX-initiated) — **not** part of this problem |

This is also the first instance of a broader category — **deterministic UX defaults**: behavior
decisions (not data decisions) that the generator must make uniformly and an app may want to vary
per entity. The manifest shape chosen here sets the precedent.

## 2. Requirements

**FR-1 (PRG everywhere).** The generated create handler MUST implement Post/Redirect/Get: respond
`303 See Other` (`RedirectResponse`) to a GET destination. The dead `HX-Redirect` pattern is
removed. A browser refresh on the destination MUST NOT re-submit the form.

**FR-2 (default destination = detail).** The default post-create destination is the new record's
detail page: `GET /ui/{entity}/{pk}?created=1`. The handler does `session.commit();
session.refresh(obj)` before redirecting — uniform over Python-side (`cuid()`/`uuid()`
`default_factory`) and DB-side (int autoincrement) PKs.

**FR-3 (stateless confirmation flash).** The destination template MUST render a confirmation
banner — `✓ {Entity} stored.` — when the `created` query param is present. Mechanism is a query
param read in the route and passed to the template context (no cookies, no session middleware, no
JS). Banner blocks are **unconditional** Jinja in `detail.html` / `list.html` / `form.html`
(rendered only when the context flag is set) — the templates are identical with and without a
manifest, so their artifact kinds stay schema-only.

**FR-4 (per-entity `on_create` knob).** A per-entity manifest field selects the destination:

| value | redirect target | use case |
|---|---|---|
| `detail` *(default)* | `/ui/{e}/{pk}?created=1` | standard CRUD — see what was stored |
| `list` | `/ui/{e}?created={pk}` | table-centric entities |
| `form` | `/ui/{e}/new?created={pk}` | rapid sequential entry |
| `confirmation` | `/ui/{e}/{pk}/created` | explicit hand-off page |

Unknown values fail loud at parse time (closed vocabulary, consistent with manifest house rules).
Omitted entity / absent manifest ⇒ `detail`. **Home: a new top-level `forms:` section in
`views.yaml`** (OQ-1 resolved):

```yaml
views: [...]          # composite-view archetypes — view_codegen's section, unchanged
forms:                # per-entity post-submit behavior — backend_codegen's section
  Profile: { on_create: detail }
  Activity: { on_create: form }       # rapid sequential entry
```

The backend-side parser (`backend_codegen/forms_manifest.py`) reads only `forms:`, tolerates a
missing/empty `views:` list, fails loud on unknown keys/values, and validates entity names against
the schema at render time. `view_codegen` and the wireframe are untouched (`parse_views()` ignores
unknown top-level keys — verified).

**FR-5 (`confirmation` archetype).** When `on_create: confirmation`, the generator emits one
additional owned template per entity (`{e}/created.html`: stored field values + links to *view /
add another / back to list*) and one route (`GET /ui/{e}/{pk}/created`).

**FR-6 (update parity).** The update handler gets the same PRG fix: `303` to
`/ui/{e}/{pk}?updated=1`, with an `✓ {Entity} updated.` banner. (Update destination is **not**
configurable in v1 — detail only.)

**FR-7 (drift & headers).** Manifest-dependent artifacts carry a `forms-sha256` header and a
distinct kind per dep-set (the `htmx-base`/`pages-base` precedent): `app/web.py` is
`fastapi-web` without a manifest, `fastapi-web-forms` (2-hash) with one; `{e}/created.html` is
`htmx-created` (2-hash — its existence depends on the manifest). Per-entity list/detail/form
template kinds are unchanged (see FR-3). Drift stale-reason + re-render dispatch follow the
existing `_PAGES_KINDS` path.

**FR-8 (no-PK fallback).** Entities without a usable PK route (no detail page) fall back from
`detail`/`confirmation` to `list` behavior. Decided deterministically at generation time
(pk-presence is static) and recorded as a comment in the emitted handler — never a hard error.

**FR-9 (tests).** Unit tests assert: 303 status + `Location` on create/update; banner rendering
with and without the query param; per-`on_create`-value route/template emission; loud failure on
unknown `on_create`. The guarded runtime smoke test (`test_runtime_smoke.py`) extends to follow
the redirect and assert the banner appears in the destination HTML.

**FR-10 (REST API untouched).** The JSON CRUD routes (`/api/...`) keep their current semantics
(201 + body). This spec governs only the HTML `/ui/` surface.

## 3. Non-Requirements

- **No session/flash middleware, no cookies** — the stateless `$0` skeleton stays stateless.
- **No JS toasts/animations** — plain HTML banner in owned templates.
- **No delete-flow change** — the HTMX row-swap delete with `hx-confirm` already works.
- **No i18n** — banner strings are fixed English placeholders (bucket-2 content; real copy is
  bucket-4, owner: the commissioning company).
- **No `on_update`/`on_delete` knobs in v1** — create only; update is fixed-detail (FR-6).
- **No validation-error re-render redesign** — the inline `/validate` blur endpoint is unchanged;
  server-side rejection behavior on final submit is out of scope here (pre-existing gap, noted).

## 4. Open Questions

All six v0.1 open questions were resolved by the planning pass — see §0. None remain.

**Post-ship follow-through (2026-06-07, same increment):** the two §0 deferrals landed, plus a
template-only polish pass:
- **OQ-3 shipped** — `startd8 wireframe` Forms section surfaces per-entity `on_create` and plans
  `created.html` for `confirmation` entities (`wireframe/plan.py:_forms_section`).
- **OQ-4 shipped (gate half)** — the manifest-extraction round-trip now runs **both** strict
  parsers over an emitted `views.yaml` (`parse_views` + `parse_forms`), so a bad `forms:` section
  fails at ingestion, not at generate time. *Deriving* `on_create` from prose remains future work.
- **Polish (bucket-2, template-only):** inline `<style>` block in `base.html` (no static mount, no
  new artifact kind); list-mode row highlight via the echoed `?created=<pk>` (OQ-6
  follow-through); "view it" link in the form-mode banner (PK entities only); HTMX delete swaps
  the row for a visible `✓ {Entity} deleted.` flash row instead of an empty body.

---

*v0.2 — Post-planning self-reflective update. 2 requirements corrected (FR-7, FR-8), 2 made more
precise (FR-2, FR-3), FR-4's manifest home decided (`forms:` section in `views.yaml`), 6 open
questions resolved (2 deferred out of v1). Defect framing (blank-page `HX-Redirect`) verified
against `htmx_generator.py:416/:458` and the plain-POST form at `:307`.*

*Spike-validated 2026-06-07 (throwaway pytest, 7/7 green, in lieu of CRP — narrow design space,
mechanical risks): (A1) `parse_views()` accepts a top-level `forms:` section unchanged — the
wireframe shares that parser (`wireframe/plan.py:770`), so both consumers tolerate it; (A3) the
blank-page defect **reproduces empirically** (plain POST → 200, body `""`, dead `HX-Redirect`
header), and `commit(); refresh(obj)` + 303 recovers the PK for both `default_factory` (cuid-style)
and int-autoincrement PKs; (A4) following the redirect renders the `?created` banner, a browser
refresh re-GETs without re-submitting, and the banner is absent without the param.*
