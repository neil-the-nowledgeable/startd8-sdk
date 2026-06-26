# Default Navigation — Implementation Plan

**Version:** 1.1 (Scope simplification — user-directed)
**Date:** 2026-06-26
**Tracks:** `DEFAULT_NAVIGATION_REQUIREMENTS.md` v0.3
**Path:** deterministic `backend_codegen` only (the only path that emits a shared base template)

> **v1.1 scope cut.** v1 ships the build-time nav + a **startup-read config** for visibility (edit +
> restart). The live runtime admin toggle (DB table, admin UI, mode-aware auth) is **deferred**
> (req NR-6). §1.3/§1.4 below are rewritten accordingly; the deferred DB/auth design is retained at
> the end of §1 as "Deferred design (parked)" so it isn't lost. Risk R1 is **eliminated**.

---

## 0. What the planning pass discovered (feeds §0 of the requirements)

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Entity UIs have a label to reuse | **No human-readable label exists** — only the class name (`Order`); href = `/ui/<name.lower()>` (`htmx_generator.py` `_entity_routes`, `crud_generator._model_names:57`) | Labels must be **derived** (title-case the class name). Trivial but net-new. |
| Views need label/href derivation | Views **already** carry `ViewSpec.name` (friendly) + `ViewSpec.route` (`view_codegen/manifest.py:139-158`, `parse_views:187`) | Views are ready to enumerate as-is. |
| "All pages visible" reuses page nav | `nav_items()` (`pages_generator.py:125-130`) **filters out** pages without `nav_label` — it is the opt-*in* path | All-visible default needs a **new** derivation: label = `nav_label or title`, never filter. |
| Admin auth is a simple gate | `app/auth.py` (`require_principal`) is emitted **only in deployed mode** (`assembler.py:273`); installed mode has **no principal at all** | Admin router must be **mode-aware**; it cannot `import .auth` in installed mode. |
| New table → create_all / alembic, done | create_all only runs in **installed** mode (`settings_renderer.should_create_all:70`); deployed uses alembic, which diffs a **schema snapshot** that will **not** contain an SDK system table absent from the user's `prisma/schema.prisma` | **Hard problem.** A runtime-DB toggle in *deployed* mode has a real migration gap. Drives the persistence design (below). |
| base.html just gets nav inlined | base.html has **two** code paths/kinds: `htmx-base` (1-hash) vs `pages-base` (2-hash) (`htmx_generator.render_base_template:180-218`) | Cleaner to emit nav as a **dedicated partial** include, isolating its multi-input hash and keeping base.html stable. |
| Owned kinds are ≤2-input | Nav depends on schema + views.yaml + pages.yaml = **3 inputs** | Net-new **3-sha header** (`_headers.py` max today is 2). |

**Resolved OQs:** OQ-2 (entity labels derived / views ready), OQ-8 (backend_codegen only).
**Escalated OQ:** OQ-7 (deployed-mode system-table persistence) is now the riskiest item.

---

## 1. Architecture

### 1.1 Build-time: deterministic nav registry
- New module `backend_codegen/nav_generator.py`:
  - `nav_registry(schema_text, views_text, pages_text) -> tuple[NavEntry, ...]` — pure, deterministic.
  - `NavEntry(key, label, href, group, source)` where:
    - **pages:** `key="page:<slug>"`, `label = nav_label or title`, `href = slug`, `group="page"`.
    - **entities:** for each `_model_names()`, `key="entity:<Name>"`, `label = titleize(Name)`,
      `href="/ui/<name.lower()>"`, `group="entity"`.
    - **views:** for each `ViewSpec`, `key="view:<route>"`, `label = view.name`, `href = view.route`,
      `group="view"`.
  - Deterministic order: group order `page → entity → view`, stable within group (declaration order
    for pages/views; schema order for entities).
- New generated artifact `app/nav.py` (kind `nav-registry`): the baked default registry as a Python
  constant `DEFAULT_NAV: list[NavItem]`, plus a `visible_nav(session) -> list[NavItem]` helper that
  subtracts hidden keys (FR-7) with a fallback to all-visible on any store error.

### 1.2 Render: nav partial template
- New generated artifact `app/templates/_nav.html` (kind `nav-partial`): iterates the nav items the
  view layer passes in; active link via `request.url.path` (reuse existing inline-style approach).
- `base.html` gains `{% include "_nav.html" ignore missing %}` at the existing nav-injection point
  (between `theme/_header.html` and `<main>`). base.html stays schema-only (`htmx-base`/`pages-base`
  unchanged) — the partial owns the multi-input hash. Resolves the two-path concern.
- A small context provider (FastAPI dependency / template global) supplies `nav_items` to every
  template render so the partial has data without each handler threading it.

### 1.3 Persistence: a startup-read config file (v1)
- Store: an optional operator-owned **config file** at app root, e.g. `nav.config.json`:
  `{"hidden": ["entity:Invoice", "view:/admin-dashboard"]}` (keys are nav `key`s). **Not** generated,
  **not** drift-tracked (SOTTO seam — like the untracked `.body.html` prose fragments). Persists across
  restarts because it's a file.
- **Load once at startup.** `app/nav.py` exposes `load_hidden() -> frozenset[str]` that reads the file
  at import/startup. Missing / empty / malformed ⇒ empty set ⇒ **all visible** (safe fallback; never
  raises into a request). To change visibility: edit the file, restart.
- No DB table, no `create_all`/alembic involvement, no per-request query. This is what eliminates the
  v0.2 deployed-mode migration gap (former R1).

### 1.4 Resolution at render
- `visible_nav() = [item for item in DEFAULT_NAV if item.key not in load_hidden()]`, exposed to every
  template render via a context provider (FastAPI dependency / Jinja global) so `_nav.html` just
  iterates. Active link via `request.url.path` (reuse existing inline-style approach).
- No admin surface, no auth coupling in v1 (req FR-15).

### 1.5 Drift / owned kinds
- New kinds: `nav-registry`, `nav-partial` (the admin-router kind is deferred with NR-6).
- `_headers.py`: add `header_nav(source_file, schema_sha, views_sha, pages_sha, kind)` (3-sha).
- `drift.py`: add the kinds to a `_NAV_KINDS` frozenset; map each to a re-render lambda in
  `_renderers()`; thread `views_text`+`pages_text` through `check_drift`/`owned_file_in_sync`
  (already threaded for forms/pages — extend the nav kinds to consume both).
- The `nav.config.json` file itself is never an owned kind and never participates in `--check`.

### 1.6 Assembler wiring
- `assembler.render_backend()`: **always** emit `app/nav.py` + `app/templates/_nav.html` (FR-3/13).
  No startup DB bootstrap needed (config is a plain file read).

---

### Deferred design (parked — NR-6, for when the live toggle is revisited)
The v0.2 live-toggle design is preserved here so it isn't lost:
- **System table** `nav_visibility(key PK, hidden, updated_at)`, *not* in the user contract, created by
  a mode-invariant idempotent `ensure_nav_tables(engine)` (`CREATE TABLE IF NOT EXISTS`) at startup —
  sidesteps the alembic schema-snapshot gap (rejected alternative: inject into the migration snapshot).
- **Mode-aware admin router** `app/nav_admin.py` (kind `nav-admin-router`): deployed gates with
  `require_principal` (imports `.auth`, self-describes mode in header like `python-settings`);
  installed is unauthenticated single-user-local with a loud banner. Renderings differ by body+hash,
  not presence (R1-S5 precedent).
- The startup config (v1, §1.3) and a future DB toggle can coexist: config = baked default overrides;
  DB = live overrides on top.

---

## 2. Step sequence

- **M0 — Registry core.** `nav_generator.py` + `NavEntry` + deterministic enumeration over
  pages/entities/views. Unit tests: ordering, key stability, label derivation, all-visible default.
- **M1 — Render seam.** `app/nav.py` (`DEFAULT_NAV` constant + `load_hidden()` + `visible_nav()`) +
  `_nav.html` partial + base.html include + template context provider. Owned kinds
  `nav-registry`/`nav-partial` + 3-sha header + drift renderers + skip threading. `--check` clean on a
  regenerate.
- **M2 — Config visibility.** `load_hidden()` reads `nav.config.json` at startup; `visible_nav()`
  subtracts; missing/malformed ⇒ all-visible fallback. Unit + runtime smoke: edit config → restart →
  item gone from nav; route still reachable (FR-9).
- **M3 — Defaults & coexistence.** Default-on for every `generate backend`; coexist with
  presentation_polish theme seam; wireframe/advisory mention; opt-out flag `--no-nav` (OQ-3); config
  location/format decided (OQ-9).

*(Former M3 "admin toggle" and M5 "deployed-mode proof" are deferred with NR-6.)*

---

## 3. Risks
- **R1 — ~~Deployed-mode persistence~~ ELIMINATED by the v1.1 scope cut.** No DB table → no alembic
  gap. (Returns only if the NR-6 live-toggle is revisited.)
- **R2 — Key stability.** Slug/entity/route renames change keys → a config entry for the old key stops
  matching, item reverts to visible (OQ-6). Document as accepted v1 behavior; no rename-migration.
- **R3 — 3-input drift. ✅ RESOLVED by spike (`SPIKE_RESULT_R3_drift.md`).** Falsified: 3-sha headers
  already ship (`header_ai_layer`), `owned_file_in_sync` already threads `views_text`+`pages_text`, no
  new regex needed (reuse `forms-sha256`+`pages-sha256`). Real `check_drift`/`owned_file_in_sync`
  return `in_sync`/`True` on the wireframe fixture; any-input change → `stale`; unthreaded → safe
  `False`. 9 spike tests + 74 existing drift tests green. The `forms:`/`editors:` bug class does NOT
  recur.
- **R4 — Always-on regression surface (now the highest, but bounded).** The new `_nav.html` is purely
  additive (74 existing tests confirm no existing file changes). **However** the `base.html` include
  line *does* change base.html by one line → a **one-time re-stamp of every existing app's base
  template** on next regenerate. This is a normal generator-version regen, but FR-14's "base.html
  unchanged" wording is imprecise — corrected to "gains exactly one deterministic include line, once."
  Golden-tree fixtures must be updated for that one line.
