# Default Navigation Requirements

**Version:** 0.3 (Scope simplification — user-directed)
**Date:** 2026-06-26
**Status:** Draft (planning-corrected + scope-cut; CRP review offered next)
**Owner:** SDK / deterministic codegen (bucket 1, `backend_codegen`)
**Scope decisions (locked with requester):**
- **Nav scope:** *all* navigable surfaces — content pages (`pages.yaml`) + entity CRUD UIs (schema-derived `/ui/<entity>`) + views (`views.yaml` dashboards/boards/workspaces).
- **Persistence (v0.3):** a **runtime config file read once at app startup**. Edit it, restart, applied; it persists because it's a file on disk. No DB table, no migration coupling.
- **Operator (v0.3):** whoever can edit the config file + restart the app (operator/author). **No in-app live toggle in v1.**
- **Deferred:** the live runtime admin toggle (DB-backed, no-restart) + admin UI + auth gating — pulled out of v1 because local-mode users can simply restart after a config change, which removes the hardest risk (the deployed-mode alembic system-table gap).

---

## 0. Planning Insights (Self-Reflective Update)

> **v0.3 scope cut (user-directed).** The live runtime admin toggle, its `nav_visibility` DB table,
> the admin UI, and the deployment-mode auth coupling are **deferred** (see §4 NR-6). Rationale:
> local-mode users can edit a config file and restart, so visibility becomes a **startup-read config**
> rather than a live DB toggle. This dissolves the central risk from v0.2 (the deployed-mode alembic
> system-table gap, R1) and removes FR-8a/FR-15's auth coupling from v1. The build-time half (FR-1..5,
> FR-10..14) is unchanged. Affected: FR-6, FR-7 rewritten; FR-8/8a, FR-15 → deferred.
>
> This section records what changed between v0.1 (pre-planning) and v0.2 (post-planning). Planning
> against `backend_codegen` falsified six assumptions and escalated one open question into the
> central design risk. See `DEFAULT_NAVIGATION_PLAN.md` §0 for the code-grounded discovery table.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Entity UIs carry a label to reuse | No human-readable label exists — only the class name; href = `/ui/<name.lower()>` | **FR-1a** added: entity labels are *derived* (title-cased class name). |
| Views need label/href work | Views already expose `ViewSpec.name` + `ViewSpec.route` | **FR-1b** notes views enumerate as-is. |
| All-visible default reuses page nav | `nav_items()` *filters out* pages lacking `nav_label` (it is the opt-in path) | **FR-2** sharpened: a *new* derivation, `label = nav_label or title`, never filtered. |
| Admin auth is a simple gate | `app/auth.py` / `require_principal` exists **only in deployed mode**; installed mode has no principal | **FR-15** rewritten mode-aware; **FR-8a** added (mode-coupled admin router). |
| New table → create_all/alembic, done | create_all runs only in installed mode; deployed alembic diffs a schema snapshot that won't contain an SDK system table absent from the user contract | **FR-6** rewritten: a mode-invariant `CREATE TABLE IF NOT EXISTS` bootstrap; **OQ-7 → resolved approach**. |
| Inline nav into base.html | base.html has two kinds/paths (`htmx-base` 1-hash / `pages-base` 2-hash) | **FR-14** sharpened: nav ships as a *dedicated partial* include; base.html stays stable. |
| Owned kinds are ≤2-input | Nav depends on schema + views.yaml + pages.yaml (3 inputs) | **FR-12** notes a net-new 3-sha header — first of its kind. |

**Resolved open questions:**
- **OQ-2 → Resolved.** Entity labels are *derived* (title-case the class name); views use `ViewSpec.name`/`.route` as-is; page labels fall back `nav_label or title`. Folded into FR-1a/1b/2.
- **OQ-7 → Resolved (approach chosen).** Persist in a generated **system table** *not* in the user
  contract, created by a mode-invariant idempotent `CREATE TABLE IF NOT EXISTS` bootstrap at startup —
  decoupling it from create_all (installed) and the alembic snapshot chain (deployed). See FR-6.
- **OQ-8 → Resolved.** This applies to the **deterministic `backend_codegen` path only** — the only
  path that emits a shared base template. The LLM/polyglot path has no shared layout to inject into.
- **OQ-1 → Resolved.** Installed mode has no principal: the admin toggle is unauthenticated
  single-user-local (loud banner); deployed mode gates it with `require_principal`. See FR-15.

**Still open after planning:** OQ-3 (opt-out flag), OQ-4 (per-request query vs cache), OQ-5 (confirm
hidden ≠ unreachable), OQ-6 (key stability on rename). These are tuning/confirmation questions, not
blockers.

---

## 1. Problem Statement

Every deterministically generated startd8 app already produces multiple navigable surfaces —
content pages, per-entity CRUD UIs, and composite views — but there is **no app-wide top
navigation** that lets a user discover and move between them. Worse, the only nav that exists today
is **opt-in and content-pages-only**: a page appears in the menu *only* if it declares `nav_label`
(or an explicit `nav:` override is hand-authored in `pages.yaml`). Entity UIs and views never appear
in a shared menu at all.

We want a **default top navigation menu** that is present in *every* generated app, lists *every*
generated navigable surface **by default** (opt-out, not opt-in), and whose per-item visibility an
admin can **toggle at runtime** with the choice **persisting across restarts**.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Content pages (`pages.yaml`) | Appear in nav **only if** `nav_label` set; nav built at $0 build time, baked into `base.html` | Default should be *visible*; today default is *hidden* |
| Entity CRUD UIs (`/ui/<entity>`) | Generated, reachable, but **never** in any shared nav | Not enumerated into nav at all |
| Views (`views.yaml`) | Generated, reachable, but **never** in any shared nav | Not enumerated into nav at all |
| Apps with **no `pages.yaml`** | Get **no nav** at all (nav is gated on `pages.yaml` presence) | Should still get a nav listing entities/views |
| Per-item visibility | Static: baked at build time, identical across restarts | No restart-persistent hide/reveal applied without a regenerate |
| Operator control | Author edits `pages.yaml` + regenerates | No config-driven, restart-applied visibility (live in-app toggle deferred — NR-6) |

---

## 2. Goals & Non-Goals (intent)

**Goals**
- A single, consistent top nav on every generated app, present by default with zero manifest authoring.
- All three navigable surface classes enumerated into one menu.
- An operator can hide/reveal any item via a startup-read config file; the choice persists across
  restarts (it's a file). **No live in-app toggle in v1** — edit config, restart.
- The feature must not break **byte-identical deterministic generation** ($0, idempotent, `--check`-clean).

**Non-Goals (intent — refine in §3 Non-Requirements)**
- Not building a live runtime admin toggle / admin UI in v1 (deferred — NR-6).
- Not building authorization/route-gating (hiding from nav ≠ blocking the route).
- Not building nested/multi-level menus, breadcrumbs, or a sidebar in v1.
- Not an end-user personalization feature (per-user nav); visibility is **app-global**.

---

## 3. Requirements

### A. Enumeration & default membership

- **FR-1 — Single nav registry.** The SDK shall compute, deterministically at build time, a
  **nav registry**: an ordered list of nav entries, one per navigable surface, aggregating
  content pages, entity CRUD UIs, and views. Each entry carries a stable `key`, a display `label`,
  an `href`, a `group` (page | entity | view), and a `source` provenance.
  - **FR-1a — Entity labels are derived.** Entity UIs carry no human-readable label in generated
    code (only the class name; href `/ui/<name.lower()>`). The registry shall derive a label by
    title-casing the entity name deterministically. `key = "entity:<Name>"`.
  - **FR-1b — View entries use the manifest as-is.** Each view contributes `label = ViewSpec.name`,
    `href = ViewSpec.route`, `key = "view:<route>"`. No derivation needed.
- **FR-2 — All-visible default (opt-out).** Every enumerated surface is a member of the nav **by
  default**. Visibility is opt-*out*, inverting today's `nav_label` opt-in for content pages. The
  page label shall fall back `nav_label or title` so a page with no `nav_label` still appears (this is
  a *new* derivation — the existing `nav_items()` filter must not be reused unchanged).
  `key = "page:<slug>"`.
- **FR-3 — Nav present without `pages.yaml`.** An app that declares only a schema (entities, no
  `pages.yaml`) shall still receive a top nav listing its entity UIs (and views, if any). The nav is
  no longer gated on `pages.yaml` presence.
- **FR-4 — Stable, regeneration-durable keys.** Each nav entry's `key` shall be derived
  deterministically from stable identity (e.g. entity name / slug / view route), so a config entry
  keyed by `key` keeps referring to the same surface across a regenerate as long as the surface still
  exists.
- **FR-5 — Deterministic ordering & grouping.** The default order is deterministic and stable across
  regenerations (e.g. grouped page → entity → view, alpha within group; refine in planning).

### B. Visibility configuration (startup-applied)

- **FR-6 — Visibility from a startup-read config file.** Per-item visibility shall be read from an
  optional **runtime config file** (e.g. `nav.config.json`, or a `[nav]` section in the app's runtime
  settings) loaded **once at app startup**. The config lists hidden nav `key`s (and/or per-group
  toggles). It is **not** a generation input (editing it does **not** require `generate backend`) and
  **not** the user's `prisma/schema.prisma`. It persists across restarts because it is a file on disk;
  to change visibility the operator edits it and **restarts**. No DB table, no migration coupling.
- **FR-7 — Nav rendered against the startup-resolved set.** The rendered top nav = (default registry)
  **minus** the keys marked hidden in the config loaded at boot. A missing/empty/malformed config
  resolves to **all visible** (safe fallback) — the app must never fail to render nav because of config.
- **FR-8 — Absent config ⇒ full default nav.** With no config file present, every enumerated surface
  is shown (FR-2). The config is purely subtractive over the deterministic default.
- **FR-9 — Hidden ≠ unreachable.** Hiding an item removes it from the menu only. The underlying route
  remains reachable by direct URL (no authorization change). (See OQ-5.)

### C. Determinism / SOTTO seam (the crux)

- **FR-10 — Byte-identical generation preserved.** The generated nav registry module and nav partial
  shall be deterministic and produce byte-identical output for identical inputs. `generate backend
  --check` stays clean.
- **FR-11 — Config is not generated, not drift-tracked.** The `nav.config` file is operator-owned
  runtime input, never written by the generator and never participating in `--check`. This is the
  hash-exempt, presence-gated seam (SOTTO): the default nav is baked deterministically; the config
  subtracts from it at startup. (Same pattern as the untracked prose `.body.html` fragments.)
- **FR-12 — New owned kinds + drift renderers.** Newly generated artifacts (nav registry module
  `app/nav.py`, nav partial `app/templates/_nav.html`) shall register as **owned deterministic kinds**
  with drift renderers, provenance headers, and skip-hook threading, so they are recognized as
  $0-owned and never fall through to LLM generation. The nav artifacts depend on **three** inputs
  (schema + `views.yaml` + `pages.yaml`), requiring a net-new **3-sha provenance header** (the first
  artifact to exceed today's 2-hash maximum) and both manifests threaded through
  `check_drift`/`owned_file_in_sync` (the `forms:`/`editors:` skip-threading bug class — verify nav
  files are recognized $0-owned, not fallen through to LLM).

### D. Integration & defaults

- **FR-13 — On by default for all deterministic projects.** The top nav is emitted by default for
  every `generate backend` run (no flag required to get it). (See OQ-3 for opt-out flag.)
- **FR-14 — Rendered as a dedicated partial included by base.html.** The nav ships as its own owned
  artifact `app/templates/_nav.html` (carrying the 3-input hash), included by `base.html`
  (`{% include "_nav.html" ignore missing %}`) at the existing nav-injection point. The partial owns
  the multi-input hash; base.html's own kind (`htmx-base`/`pages-base`) stays schema/2-input as today.
  **Note (spike-corrected):** adding the include line changes base.html by exactly one line — a
  one-time, deterministic re-stamp of every existing app's base template on next regenerate (not
  "unchanged"). The nav coexists with the `presentation_polish` theme seams (`theme/_header.html`,
  static CSS mount) without conflict.
- **FR-15 — No admin surface / no auth coupling in v1.** v1 ships **no** in-app toggle, so there is no
  admin router and no deployment-mode auth coupling. (The live admin toggle + its `require_principal`
  gating are deferred — NR-6.) This removes the v0.2 installed-vs-deployed auth fork entirely.

---

## 4. Non-Requirements

- **NR-1** No per-user / per-session nav personalization. Visibility is app-global.
- **NR-2** No route authorization or access control derived from nav visibility (hiding hides the
  link only — FR-9).
- **NR-3** No nested menus, mega-menus, breadcrumbs, sidebars, or reordering UI in v1 (order is
  deterministic/build-time).
- **NR-4** No author-time `hidden:` manifest field in v1 — visibility lives in the startup-read config
  (FR-6), not in a generation manifest (so changing it needs a restart, not a regenerate).
- **NR-5** No change to how routes themselves are generated; this feature only *enumerates* and
  *links* existing routes.
- **NR-6 (deferred to a later version)** The **live runtime admin toggle** — an in-app UI that flips
  visibility without a restart, persisted in a `nav_visibility` DB table, gated by deployment-mode
  auth — is explicitly **out of v1**. It is deferred because local-mode users can edit the config and
  restart (FR-6), and building it would re-introduce the deployed-mode alembic system-table problem
  and the installed-vs-deployed auth fork. When revisited, the v0.2 design (mode-invariant
  `CREATE TABLE IF NOT EXISTS` bootstrap + mode-aware `require_principal` admin router) is the starting
  point — preserved in git history and `DEFAULT_NAVIGATION_PLAN.md`.

---

## 5. Open Questions

**Resolved by the planning pass** (see §0): OQ-1 (installed-mode auth), OQ-2 (entity/view labels),
OQ-7 (deployed-mode persistence), OQ-8 (backend_codegen-only breadth).

**Closed by the v0.3 scope cut:** OQ-1 and OQ-7 are now moot — no auth coupling and no DB/migration
persistence (config-at-startup replaces both). OQ-4 (render-cost of a per-request DB lookup) is moot:
config is loaded once at startup, not queried per request.

**Still open** (tuning/confirmation — not blockers):

- **OQ-3 — Opt-out flag.** Given FR-13 makes nav default-on, should there be a build-time way to
  *suppress* the whole nav (or a per-group suppression, e.g. "no entity UIs in nav")? Leaning: a single
  `--no-nav` escape hatch; per-group suppression deferred.
- **OQ-5 — Hidden-route semantics.** Confirm hiding never gates the route (FR-9). If some surfaces
  *should* become unreachable when hidden, that is a separate authorization feature — out of scope here.
- **OQ-6 — Key stability vs. rename.** If a page slug / entity name / view route changes, its `key`
  changes and a config entry for the old key no longer matches (item reverts to visible). Accepted v1
  behavior (no rename-migration), or do we need stable surrogate keys? Leaning: accept; document.
- **OQ-9 — Config location & format.** Where does `nav.config` live and in what format — a standalone
  `nav.config.json` at app root, a `[nav]` section in the runtime settings, or an env var? Leaning:
  standalone JSON at app root (simplest to hand-edit; no settings coupling). Confirm in planning.

---

*v0.3 — User-directed scope simplification on top of the v0.2 self-reflective update. The live runtime
admin toggle (DB table + admin UI + deployment-mode auth) is **deferred** (NR-6); visibility now comes
from a startup-read config file (FR-6) applied on restart. This dissolved the central v0.2 risk (the
deployed-mode alembic system-table gap) and removed the installed-vs-deployed auth fork. Net: FR-6/7/8
rewritten, FR-8a/FR-15 retired into NR-6, OQ-1/4/7 closed, OQ-9 added. The build-time half (FR-1..5,
FR-10..14) is unchanged. CRP review still offered next.*
