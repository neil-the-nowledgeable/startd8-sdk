# Filtered / faceted list views (P0-2) + `list of text` type (G3) — Requirements

**Version:** 0.2 (post-investigation)
**Date:** 2026-06-10
**Status:** IMPLEMENTED 2026-06-10 — FR-FL-1..6 (`filters:` in views.yaml → faceted/JSON-membership/
search list handler + GET filter form) and G3 (`list of text` → `String[]`). Runtime-proven (TestClient:
scalar facet, JSON-array membership, case-insensitive search all narrow). 357 passed.
**Scope:** strtd8 `RESUME_LIBRARY_ARCHETYPE_GAPS` **P0-2** (shared-floor archetype, confirmed by the
shared-floor answer — navig8's `Citation`/`TreeNode` want it too) + the paired `CONTRACT_GRAMMAR` **G3**
(`list of text` → `String[]`). Server-side facet + free-text filtering on generated list views, with
JSON-array *membership* for list fields. **$0, deterministic, 0 LLM.**
**Component:** `backend_codegen` (htmx list handler + template), `view_codegen`/manifest (`filters:`),
`manifest_extraction` (G3 prose type).

## 0. Planning insights (from a code-investigation pass)

| Assumption | Discovery | Impact |
|------------|-----------|--------|
| `filters:` needs new threading into the renderers | `render_ui(schema, src, pages_text, views_text)` **already receives `views_text`**; views.yaml already hosts a disjoint `forms:` section parsed separately | Put `filters:` in **views.yaml** (a 3rd disjoint section, like `forms:`); zero new threading. |
| List fields filter like scalars | list fields persist as **`Column(JSON)`** (`sqlmodel_renderer`), i.e. JSON text like `["a","b"]` | JSON-array facets need **membership** (`LIKE '%"v"%'`), not `==`. The one real mechanic. |
| G3 is just a new plain-type entry | `DocField` has **no `is_list`**, and the emitter renders scalars only | G3 needs `DocField.is_list` + emitter `String[] @default([])` rendering (the parser + sqlmodel side already handle `String[]`→JSON). |
| The list handler is easy to extend | `list_<e>` is `items = session.exec(select(<Name>)).all()` — no query-param logic | Add filter/search query-building before `.all()`; empty params = full list (unchanged default). |

## 1. Functional Requirements

- **FR-FL-1 — `filters:` manifest.** views.yaml may carry a top-level `filters:` section mapping each
  entity to `{facets: [field, …], search: [field, …]}`, strict-parsed (unknown keys / unknown field
  refs fail loud, against the contract). Verify: a valid block parses; an unknown entity/field raises.

- **FR-FL-2 — Faceted filtering (server-side, exact + JSON membership).** The generated `list_<e>`
  handler reads a query param per `facets` field and narrows rows: a **scalar** facet matches `== value`;
  a **list (`Column(JSON)`)** facet matches **membership** (the value appears in the array). Empty/absent
  param ⇒ no narrowing. Verify: `?status=active` returns only active rows; `?tags=python` returns rows
  whose `tags` array contains `python` (not a substring of another tag); no params ⇒ all rows.

- **FR-FL-3 — Free-text search.** A `q` query param matches (case-insensitive substring) across the
  `search` fields (OR). Empty `q` ⇒ no narrowing. Verify: `?q=lead` returns rows where any search field
  contains "lead"; absent ⇒ all rows.

- **FR-FL-4 — Filter UI on the list template.** The list template renders a `GET` form: a control per
  facet (+ a search box if `search` set), preserving current values. Submitting reloads `/ui/<e>?…`.
  No JS required. Verify: the template carries the facet inputs + search box bound to the params.

- **FR-FL-5 — `list of text` prose type (G3).** The authoring grammar gains `list of text` →
  `DocField(is_list=True, prisma_type="String")`; the emitter renders `<name> String[] @default([])`
  (→ `Column(JSON)` downstream). Verify: `| tags | list of text | no |` emits `tags String[]
  @default([])` that round-trips; a list facet over it filters by membership (ties FR-FL-2).

- **FR-FL-6 — Inert without `filters:`.** An entity with no `filters:` entry emits the current static
  list (byte-identical) and an unfiltered handler. Verify: no-filter entities are unchanged.

## 2. Non-Requirements

- **No pagination/sort** (separate asks; OQ-E reserved keys → reject for now).
- **No LLM / no client JS** — server-side GET form, deterministic.
- **Not a query DSL** — facets are equality/membership; search is substring. Range/comparison out.
- **Two-hop / relation filtering out** — facets are the entity's own columns only.

## 3. Open Questions

- **OQ-FL-1 — JSON membership portability.** `LIKE '%"v"%'` over the JSON text is the SQLite-locked
  approach (correct for the contract's quoted-string arrays). If a non-SQLite target appears, revisit
  with `json_each`. (Resolved-for-now: SQLite is the locked target.)
- **OQ-FL-2 — facet control type.** A `<select>` of distinct existing values vs a free `<input>`.
  Lean: `<input>` for v1 (no extra query to enumerate distinct values); a select is a follow-on.

## 4. Acceptance

1. `filters:` parses strict; unknown field/entity → loud.
2. Scalar facet, JSON-membership facet, and free-text search each narrow correctly server-side; empty =
   full list; combined params AND together.
3. `list of text` emits `String[] @default([])`, round-trips, and is membership-filterable.
4. No-filter entities are byte-identical (FR-FL-6).
