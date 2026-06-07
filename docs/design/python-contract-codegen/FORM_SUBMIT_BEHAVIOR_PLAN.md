# Form Post-Submit Behavior — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-07
**Status:** Plan (post-exploration)
**Requirements:** `FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md` (v0.2)

---

## Discoveries (planning pass over the v0.1 requirements)

| v0.1 Assumption | Planning Discovery |
|---|---|
| `on_create` lives "in views.yaml" as a per-view-ish field | `views.yaml` is the **class-3 composite-view** manifest; entries are views (`name/kind/route/root`), not entities. BUT `parse_views()` does **not reject unknown top-level keys** — a sibling top-level `forms:` section is non-breaking for `view_codegen` and the wireframe. Two strict parsers over disjoint sections of one file, mirroring how `pages.yaml` is shared by `pages_generator` and `htmx_generator` (base-nav). |
| A views.yaml could carry only form config | `parse_views()` raises on zero views (`"views.yaml declares no views"`). The **backend-side `forms:` parser must therefore tolerate a missing/empty `views:` list** — it reads only its own section. |
| Handler needs `session.refresh(obj)` to learn the PK | Partially. `cuid()`/`uuid()` PKs are **Python-side `default_factory`** (`sqlmodel_renderer.py:83-85`) — `obj.id` exists pre-commit. Int-autoincrement PKs are DB-side. `session.commit(); session.refresh(obj)` covers both uniformly. |
| Banner requires template variants per `on_create` mode | **No.** Banner blocks are unconditional Jinja (`{% if created %}…`) in `detail/list/form` templates; routes always pass the query param through. **Only `app/web.py` routing + the emitted-artifact set vary with the manifest** — big drift simplification: template kinds (`htmx-detail` etc.) stay 1-hash schema-only. |
| Manifest-driven artifacts need a 2-hash header | Confirmed, with an exact precedent: distinct kind per dep-set (`htmx-base` vs `pages-base`, `drift.py:33-55`; `python-requirements[-authoring][-ai]`, `derived.py:243-246`). `app/web.py`: kind `fastapi-web` (no manifest) vs `fastapi-web-forms` (+ `forms-sha256` header). `{e}/created.html` (kind `htmx-created`) is 2-hash — its *existence* depends on the manifest. |
| Detail redirect carries `?created={pk}` | Redundant — pk is already in the path. `detail` → `?created=1`; `list`/`form` → `?created={pk}` (enables future row-highlight, OQ-6). |
| HTMX may interact with the 303 | No interaction: the form is a plain browser POST; 303+GET is native. The blur-validate `hx-post` endpoint and the HTMX delete row-swap are untouched. |
| FR-8 fallback "logged in the generation report" | There is no generation report; the fallback is decided **at generation time** (pk known statically) — emit a code comment in the handler instead. Wireframe surfacing deferred (OQ-3 → not v1). |

## Step plan

Order is dependency-safe; each step keeps the suite green.

1. **PRG defect fix + default behavior (FR-1, FR-2, FR-3, FR-6, FR-8)** — `htmx_generator.py`
   - `_entity_routes()`: `create_{e}` → `session.commit(); session.refresh(obj)`;
     `RedirectResponse("/ui/{e}/{pk}?created=1", status_code=303)` when pk exists, else
     `RedirectResponse("/ui/{e}?created=1", 303)` (fallback comment). `update_{e}` →
     303 to `/ui/{e}/{pk}?updated=1`. Remove both `HX-Redirect` responses.
   - Routes `list_{e}` / `new_{e}` / `detail_{e}` pass `created` (+ `updated` on detail) from
     `request.query_params` into template context.
   - `render_web()` imports `RedirectResponse`.
   - Templates: banner block at top of `content` in `list/detail/form` —
     `{% if created %}<p class="flash">✓ {Entity} stored.</p>{% endif %}` (detail also
     `{% if updated %}…updated.{% endif %}`). Kinds unchanged.
2. **`forms:` manifest parser (FR-4)** — new `backend_codegen/forms_manifest.py`
   - `parse_forms(text) -> Mapping[str, str]` (entity → `on_create`), strict: closed vocabulary
     `{detail, list, form, confirmation}`, unknown keys/values/entities fail loud; tolerates
     missing/empty `views:`; `forms_sha256()` helper. Entity refs validated against the schema at
     render time (parser is schema-blind, mirroring `parse_views(known_entities=…)` shape).
3. **Manifest-driven routing + confirmation archetype (FR-4, FR-5)** — `htmx_generator.py`
   - `render_web(schema_text, source_file, forms_text=None)`: per-entity destination from the
     manifest (default `detail`); `confirmation` adds route `GET /ui/{e}/{pk}/created`.
   - `render_created_template()` (kind `htmx-created`, 2-hash header): stored values +
     view / add another / back-to-list links.
   - `render_ui(…, forms_text=None)` threads through; emits `{e}/created.html` only for
     `confirmation` entities. `web.py` kind: `fastapi-web` vs `fastapi-web-forms` (2-hash).
4. **Drift (FR-7)** — `backend_codegen/drift.py`
   - `forms-sha256` header regex + `embedded_forms_sha()`; `_FORMS_KINDS = {fastapi-web-forms,
     htmx-created}`; stale-reason + re-render dispatch following the `_PAGES_KINDS` path.
5. **Assembler + CLI** — `assembler.py`, `cli_generate.py`
   - `assemble(…, views_text=None)`; `generate backend --views <views.yaml>` (same file the
     `generate views` command consumes; backend reads only `forms:`). Malformed manifest → fail
     loud (exit 2), matching `--pages` handling.
6. **Tests (FR-9)** — `tests/unit/backend_codegen/`
   - `test_htmx.py`: 303 + `Location` per mode; banner with/without param; created.html emission
     only under `confirmation`; loud unknown `on_create`; no-PK fallback; byte-idempotence.
   - `test_cli_backend.py`: `--views` flag, `--check` with/without manifest.
   - `test_runtime_smoke.py`: follow create redirect (`follow_redirects`), assert banner text in
     destination HTML; refresh (re-GET) does not duplicate the record.

**Not in plan (confirmed out):** sessions/cookies, `on_update`/`on_delete`, delete-flow changes,
REST `/api` changes, i18n, manifest_extraction round-trip learning (`forms:` is optional —
defaults apply when absent; revisit when kickoff ingestion derives it).
