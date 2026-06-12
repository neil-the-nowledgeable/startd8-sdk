# `editors:` Archetype — Bulk Child-Field Editor (Requirements)

**Version:** 0.3 (Post-CRP — convergent-review hardened)
**Date:** 2026-06-12
**Status:** Draft (planning-corrected + CRP R1 triaged; ready for implementation)
**Component:** `src/startd8/backend_codegen/` (a new editor archetype, sibling to CRUD / `forms:` / `filters:` / `flows:` / `views:`)
**Requested by:** StartDate (strtd8) app team — `docs/SDK_BULK_CHILD_FIELD_EDITOR_CAPABILITY_BRIEF_2026-06-11.md` (strtd8 repo)
**Owner:** startd8-sdk team
**Plan:** `EDITORS_ARCHETYPE_PLAN.md` (v1.0)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning, carrying the brief's assumptions) and v0.2 (after reading the
> `backend_codegen` machinery and empirically testing the closest precedent). The planning pass produced
> **7 corrections + 3 new requirements**, the most important driven by a **verified pre-existing bug**.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| "Follow the `flows:` precedent → editor files are `$0`/drift-clean" (FR-ED-10) | **Verified bug:** `fastapi-flow` is registered in no drift renderer; `generate backend --check` exits **1** on a clean `flows:` app (router → `tampered`; shell/aggregator → silently skipped, unprotected). | Editors **must** register an explicit drift path (the `filters:`/`forms:` model), not copy flows. FR-ED-10 rewritten; **quick win** added (FR-ED-15: fix `flows:` drift). |
| `default_value: module:fn` syntax | `flows:` `on_finish` uses a **bare fn from a fixed module**; two seam syntaxes is needless inconsistency and `module:fn` is unvalidatable at render. | OQ-1 resolved → fixed-module convention (`app/editors/resolvers.py`). FR-ED-9 updated. |
| Pre-fill from effective text **and** empty→NULL reset | These collide — saving an unchanged source-prefilled input **materializes** a default into an override, defeating reset and de-linking from the source. | OQ-2 resolved → **dirty-detection** required. FR-ED-5/6 updated; **FR-ED-12 added**. |
| Mount is free | `main.py` is always-generated + drift-tracked; adding the editor mount block re-stamps it once for every app. | OQ-4 resolved → accept the one-time drift, require inert-when-absent. **FR-ED-13 added**. |
| (not considered) | Bulk POST carries N child ids → IDOR / cross-parent / non-`included` edit surface. | OQ-5 resolved → server-side allow-list. **FR-ED-14 added**. |
| (not considered) | Author-supplied `route` can collide with `/ui/*` (CRUD), `views:`, `/flow/*`. | OQ-8 resolved → validate single `{id}` + warn on `/ui/` collision. FR-ED-2 validation extended. |
| Header machinery insufficient | `header_forms`/`header_forms_tmpl` + the `startd8-entity` slot already enable single-editor drift re-render. | No new header builder; reuse with a new `kind` + editor name in the entity slot. |

**Resolved open questions:**
- **OQ-1 → Fixed-module convention.** `default_value: <bare_fn>` from `app/editors/resolvers.py` (mirrors `flows:` `on_finish`).
- **OQ-2 → Dirty-detection (FR-ED-12).** Inputs carry their resolved default; POST stores only changed values; unchanged stays NULL.
- **OQ-3 → Explicit editors drift path (FR-ED-10).** Reuse the views.yaml-derived (`_FORMS_KINDS`-style) drift route; do **not** rely on the flows path.
- **OQ-4 → Accept one-time `main.py` drift (FR-ED-13).** Precedented by flows; block is inert when no `editors:` declared.
- **OQ-5 → Server-side id allow-list (FR-ED-14).** The handler re-derives the editable set; ignores ids outside it.
- **OQ-6 → `group_by` optional.** Flat ordered list is the v1 floor; grouping is additive.
- **OQ-7 → `<textarea>` for v1.** Widget-from-column-type deferred (non-requirement); `edit_field` is treated as free text.
- **OQ-8 → Route validation (FR-ED-2).** Exactly one `{id}` placeholder; warn on `/ui/` literal collision.

## 1. Problem Statement

The StartDate résumé wizard needs a **final-edit** surface: edit one field (`overrideText`) across a
parent's (`ResumeBuild`) filtered, grouped children (`ResumeBuildItem` where `included == true`,
grouped by `sectionKey`, ordered by `orderIndex`) in **one form/POST**, with reset-to-default. The data
and generator already support it (`ResumeBuildItem.overrideText` exists; the assembler resolves
override-or-source first — FR-RV-3). The **only** gap is the editing surface. The app team could
hand-author it (one route pair + a template in their owned wizard) but has **paused** to let the SDK
own it, because the shape is **generic**, not résumé-specific:

> "Edit a chosen field across a parent's filtered, grouped children, then save (with reset-to-default)."

If `backend_codegen` gains a **bulk child-field editor** archetype, this feature — and every future
"edit the children of X in one screen" — becomes a **manifest declaration**, generated `$0` like
CRUD / views / filters. The only app residue is a tiny app-specific **default-value resolver**.

### Gap table

| Capability | Current State | Gap |
|-----------|---------------|-----|
| Edit `overrideText` per child | Exists on `/ui/resumebuilditem` CRUD (single-row) | No **contextual, parent-scoped, bulk** editor |
| Parent→child FK scoping, `group_by`, `order_by` | Exists in `views:` (board / workspace / aggregate) | Not exposed as an **editable** surface |
| Own-column `filter` (`included == true`) | Exists in `filters:` | Not reused by an editor |
| Bulk multi-row write (one field, N children, one POST) | **Does not exist** — CRUD is single-row write | Net-new generator surface |
| Reset-to-default (empty → fall back) | n/a | Net-new |
| App-provided pre-fill/reset resolver | `flows:` has the `on_finish` owned-fn hook precedent | Needs an analogous `default_value` hook |

## 2. Requirements

### Manifest

- **FR-ED-1 — `editors:` section.** A new top-level `views.yaml` section, a **list** of editor specs,
  sibling to `views:` / `forms:` / `filters:` / `flows:`. Parsed strictly: unknown keys → loud;
  duplicate editor `name` → loud; **inert (zero artifacts) when absent**. Tolerant of an empty/missing
  section (the filters/flows precedent).
- **FR-ED-2 — Grammar.** Each editor declares:

  ```yaml
  editors:
    resume_final_edit:
      parent: ResumeBuild           # context object (id in the route)
      child: ResumeBuildItem        # rows to edit
      fk: resumeBuildId             # child → parent FK column
      edit_field: overrideText      # the single edited field (one <textarea> per child)
      filter: { included: true }    # reuse filters: own-column semantics
      group_by: sectionKey          # form sections (optional)
      order_by: orderIndex          # ordering within/across groups
      reset_to_default: true        # empty input → set edit_field = NULL
      default_value: app.resume_wizard:effective_text   # pre-fill / reset target resolver (§ hook)
      route: /resume-wizard/{id}/edit
      label: Make final edits
  ```

- **FR-ED-3 — Contract validation (loud at render).** `parent`/`child` are known entities; `fk` is a
  column on `child`; `edit_field` is a column on `child`; `group_by`/`order_by` (when present) are
  columns on `child`; `filter` keys are own-columns on `child`. Mirrors `filters:`/`flows:` validation
  posture (parse-time entity check, render-time field check where the schema is available).
  **(v0.2, OQ-8)** Additionally validate `route`: it must contain **exactly one** `{id}` placeholder;
  **warn** (non-fatal) when `route` starts with `/ui/` (CRUD namespace) to surface likely collisions.

### Generation

- **FR-ED-4 — GET editor route.** Generate `GET <route>`: load `parent` by id (404 if absent); query
  `child` rows `WHERE fk == parent.id` AND `filter`, ordered by `order_by`, grouped by `group_by`;
  render a form with **one input per child**, pre-filled from the `default_value` resolver.
  **(v0.3, R1-S7)** `filter` is a **static own-column equality map** (e.g. `{included: true}` → a
  `WHERE child.included == true` clause), **not** the `filters:` facet/search UI grammar
  (`filters_manifest.EntityFilter` is `{facets, search}` only — the editor reuses its *own-column
  validation*, not its widget grammar). The GET query and the POST allow-list (FR-ED-14) MUST derive the
  editable set from the **identical** `WHERE fk == parent.id AND <filter>` expression, so a row excluded
  by `filter` is neither rendered nor writable.
- **FR-ED-5 — POST save.** Generate `POST <route>`: parse the form; for each editable child, apply the
  dirty/reset rules (FR-ED-12); commit in **one transaction**; redirect back (PRG, the `forms:`
  post-submit precedent). **(v0.2)** Writes are restricted to the server-derived editable set (FR-ED-14).
- **FR-ED-6 — Reset-to-default.** When `reset_to_default: true`, an **empty** input sets
  `edit_field = NULL` (the row falls back to its default/source value). **(v0.2, OQ-2)** An input left at
  its pre-filled default (non-empty but unchanged) is **not** written — see FR-ED-12; only empty +
  `reset_to_default` writes NULL, only a genuinely changed value writes a string.
- **FR-ED-7 — Template.** Generate the form template (`group_by` → `<section>`s; flat ordered list when
  absent). Carries the GENERATED provenance header.
- **FR-ED-8 — Mount.** Emit a per-editor router + an aggregator (`editor_routers`) that `main.py` mounts
  via a **tolerant** `try: from .editors import editor_routers` block (the `flow_routers` precedent).

### The app seam

- **FR-ED-9 — `default_value` hook.** The pre-fill / reset-target value is each child's **effective**
  value, whose resolution is app-specific (polymorphic over the row). The archetype calls an
  **app-provided resolver** named in the manifest via a **tolerant import seam** (the `flows:`
  `on_finish` precedent): present → used for pre-fill; **absent → fall back to `edit_field` raw**
  (no-op seam, app still works). The resolver signature is `resolver(child_row, session) -> str`.
  **(v0.2, OQ-1 resolved)** `default_value` is a **bare function name** imported from the fixed
  conventional module `app/editors/resolvers.py` (`from app.editors.resolvers import <name>`), mirroring
  `flows:`' `from app.flows.finishers import <name>`. The SDK never imports the resolver at generation
  time — it emits a tolerant runtime import seam in the generated app, preserving `$0`/determinism.
  **(v0.3, R1-F5 — request-time exceptions)** The resolver **call** is guarded per-row, not just the
  import: if the resolver raises during GET pre-fill for a child, that child degrades to raw `edit_field`
  (logged), and the rest of the form still renders — one bad row must not blank the whole editor. (The
  `flows:` `on_finish` precedent guards the import but leaves the *call* unguarded; editors must not
  inherit that gap in a per-row loop.)
  **(v0.3, R1-F7 — `default_value` omitted is a first-class mode; closes OQ-10)** When `default_value`
  is omitted, there is **no resolver seam**: every input's default mirror (FR-ED-12) is the child's raw
  `edit_field` value (empty string for NULL). This zero-seam editor (`parent/child/fk/edit_field/route`
  only) is fully supported and requires **no app code**.

### Determinism & ownership

- **FR-ED-10 — `$0`, idempotent, drift-clean.** Editor artifacts are **owned**, `$0.00`-skip
  recognized, and `generate backend --check` reports them **`in_sync`** immediately after a clean
  generate. **(v0.2, OQ-3 resolved)** This requires an **explicit editors drift path** in
  `drift.py`: register `fastapi-editor` (router) + `editor-form` (template) as views.yaml-derived kinds
  (the `_FORMS_KINDS` / `_check_forms_drift` model), re-rendering the **named** editor (editor name
  recovered from the `startd8-entity:` header slot). The aggregator `app/editors/__init__.py` carries a
  real `# GENERATED from` + sha header so it is either drift-protected or cleanly recognized — **never
  the silent-skip state the flow aggregator/shell fall into.** A generate→`--check` round-trip with an
  `editors:` section present is the acceptance gate.
  **(v0.3, R1-F1 — both kinds must resolve a renderer)** Adding a kind to the views.yaml-derived set
  WITHOUT a matching `_forms_renderers()`/`_editors_renderers()` entry returns `tampered` (the "unknown
  forms-configured kind" branch) — reproducing the flows bug for the template. So **both** `fastapi-editor`
  AND `editor-form` must (a) be in the drift kind-set and (b) have a renderer entry, and the `editor-form`
  template must be **header-bearing** (carries `schema-sha256`) so it is verified, never silently skipped.
  **(v0.3, R1-F2 — orphan-editor lookup-miss)** When an on-disk file's `startd8-entity` slot names an
  editor no longer present in `views.yaml` (renamed/removed, file left behind), the drift renderer MUST
  return a deterministic `tampered` (orphan) — never a `KeyError`/`None` that crashes `--check` (exit 2);
  drift is exit 1.
- **FR-ED-11 — Provider owned-kinds & skip-hook recognition.** **(v0.3, R1-S2 — corrected; was false as
  written)** The prime-contractor `$0.00`-skip predicate `owned_file_in_sync(schema_text, ondisk_text)`
  calls `check_drift` with **`forms_text` unset**, so today **every** views.yaml-derived kind
  (`fastapi-web-forms`, `htmx-created`, and the planned `fastapi-editor`/`editor-form`) routes to
  `_check_forms_drift(forms_text=None)` → `ERROR` → returns **`False`** → falls through to the LLM.
  *Verified:* a shipped `fastapi-web-forms` `web.py` is `in_sync` WITH `forms_text` but `owned_file_in_sync`
  returns `False`. Editor `$0` recognition therefore depends on **FR-ED-16** (thread `views.yaml` into the
  skip-hook). It does **not** work "automatically." This requirement is satisfied iff, after FR-ED-16,
  `owned_file_in_sync` returns `True` for in-sync editor files **and** for the shipped forms kinds.
- **FR-ED-12 — Dirty-detection (no accidental materialization).** Each generated input carries its
  resolved **default** (the `default_value` result, or raw `edit_field` in the omitted mode — FR-ED-9) as
  a `data-default` attribute / hidden mirror. On POST, for each editable child the comparand is the
  **submitted default mirror** echoed back by the client — **(v0.3, R1-F3)** the POST MUST NOT call the
  resolver again (a GET/POST recompute could differ and silently lose a real edit or re-materialize a
  stale default). Rules: **(a)** submitted value `==` submitted mirror → **no write** (preserve
  NULL/source-tracking); **(b)** submitted value empty `and reset_to_default` → set NULL; **(c)** submitted
  value differs from mirror and non-empty → store the string. **(v0.3, R1-F8 — whitespace)** Comparison
  normalizes a single trailing newline (`<textarea>` commonly appends one) before the equality test, so a
  cosmetic `"x" → "x\n"` is **not** a spurious write. This is the correctness crux that keeps "reset"
  meaningful and prevents source text from being frozen into an override.
- **FR-ED-13 — One-time `main.py` re-stamp.** Mounting `editor_routers` adds one tolerant block to the
  always-generated `render_main`, changing `main.py` bytes **once** for every existing app on first regen
  (precedented by `flows:`). The block MUST be inert (`editor_routers = []`) when no `editors:` is
  declared, so runtime behavior is identical for non-editor apps. This drift is documented, expected, and
  resolved by a single `generate backend`.
- **FR-ED-14 — Server-side editable-set allow-list + field-level write scope (anti-IDOR /
  anti-mass-assignment).** The POST handler re-derives the editable child set on the server
  (`WHERE fk == parent.id AND filter`, the identical expression as FR-ED-4's GET) and applies writes
  **only** to children whose id is in that set; ids absent from the set (other parents, filtered-out rows,
  fabricated ids) are **ignored**, not written. No reliance on client-submitted ids for authorization.
  **(v0.3, R1-F4/R1-S4 — column scope)** The parser accepts **only** form params matching the single
  `edit_field` input-name pattern (e.g. `item-{id}`); any other param — including a crafted
  `item-{id}-<otherColumn>` — is **never** written. WHICH rows (id allow-list) and WHICH column
  (`edit_field` only) are both enforced at the POST boundary; the §3 "exactly one `edit_field`"
  non-requirement is an enforced invariant, not just a declaration.
- **FR-ED-15 — Fix `flows:` drift (a sub-case of FR-ED-16; independently shippable).** Register
  `fastapi-flow` in the **forms** drift path (`_FORMS_KINDS` + a `_forms_renderers()` entry re-rendered
  WITH `forms_text` — **not** the schema-only `_renderers()` map, which would re-render without
  `views.yaml` and false-flag `tampered`; **R1-S1**), **and** give the flow shell + aggregator real
  `# GENERATED from` + `schema-sha256` headers so they are drift-protected, not silently skipped
  (**R1-S3 — this half is load-bearing, not parenthetical**: the bug has two halves — router false-flag +
  shell/aggregator silent-skip). Verified: a clean `flows:` app currently fails `--check` with exit 1.
  Ship as a small standalone PR ahead of the archetype.
- **FR-ED-16 — Fix views.yaml-derived drift + skip-hook recognition (the shared prerequisite).**
  **(v0.3, scope widened per orchestrator decision)** The skip-hook gap in FR-ED-11 (R1-S2) and the flows
  drift gap in FR-ED-15 are the **same class** of pre-existing defect: views.yaml-derived owned files are
  not reliably recognized as `$0`. This requirement covers the shared fix across **forms + flows +
  editors**: (1) thread the `views.yaml` text into `owned_file_in_sync` (and any other skip-hook callers)
  so `_check_forms_drift` receives `forms_text` instead of `None`; (2) ensure every views.yaml-derived
  kind (`fastapi-web-forms`, `htmx-created`, `fastapi-flow`, `fastapi-editor`, `editor-form`) is in the
  kind-set **and** has a renderer entry; (3) a regression suite proving `owned_file_in_sync` returns
  `True` for in-sync instances of **all** of these (forms kinds included — they are broken today).
  FR-ED-15 is the flows slice of this; FR-ED-11 is the editor slice. **This is a prerequisite for the
  editor archetype's `$0` claim and also repairs shipped `forms:` apps.**

## 3. Non-Requirements (v1)

- **No multi-field bulk edit.** Exactly one `edit_field` per editor.
- **No child create/delete.** Edit-only over an existing child set (`included == true`); no inline
  add-row / remove-row.
- **No LLM.** Pure deterministic generation (bucket 1).
- **No client-side JS framework.** Plain browser form POST + HTMX, consistent with the rest of
  `backend_codegen`.
- **No tenancy / per-user authorization isolation.** Inherits whatever posture generated CRUD has;
  tenancy is deferred (matches `deployment-mode` Tier B). **(v0.3, R1-F6 — explicit)** The GET route has
  **no read-authorization beyond parent-existence** (404 only, never 403): anyone who can reach CRUD can
  open `<route>` for any parent id. This is the *deliberate* inheritance of the no-tenancy posture, called
  out so a later reviewer does not re-file the missing 403 as an oversight.
- **No cross-parent / global bulk edit.** Always scoped to one `parent` id in the route.

## 4. Open Questions

> **All v0.1 open questions were resolved by the planning pass (§0); CRP R1 closed OQ-10.** OQ-1→OQ-8,
> OQ-10 are closed. One remains:

- **OQ-9 (open) — Resolver provenance.** Should the archetype emit a stub `app/editors/resolvers.py`
  (declared fn names as `NotImplementedError` placeholders) to make the seam discoverable, or stay fully
  tolerant (no stub)? Trade-off: discoverability vs. an extra owned file. *(Lower stakes now that the
  omitted-resolver mode is first-class — FR-ED-9/R1-F7.)*
- **OQ-10 → CLOSED (R1-F7).** `default_value`-omitted is a first-class zero-seam mode; the default mirror
  falls back to raw `edit_field`. Folded into FR-ED-9 + FR-ED-12.

## 5. Quick Wins / Low-Hanging Fruit (surfaced by planning)

1. **FR-ED-15 — `flows:` drift fix.** Independently shippable; fixes a verified CI-breaking bug for
   existing `flows:` apps. The editor work builds the exact machinery anyway.
2. **`default_value`-omitted mode (OQ-10).** A zero-seam editor (just `parent/child/fk/edit_field/route`)
   is trivially derivable and covers simple "edit a plain column across children" cases with no app code
   at all — broader reuse than the résumé motivating case for ~zero extra cost.
3. **Reuse over rebuild.** The parent-scoped query (`view_codegen` board/aggregate), filter WHERE
   (`filters_manifest`), POST-parse + PRG (`htmx_generator`), and header/entity-slot drift machinery all
   already exist — the net-new surface is one transaction-bounded bulk write + dirty/reset logic.

---

*v0.2 — Post-planning self-reflective update. 4 requirements narrowed/corrected (FR-ED-5/6/9/10),
3 added (FR-ED-12/13/14), 1 quick-win added (FR-ED-15), 8 open questions resolved, 2 new CRP-level
questions opened. Centerpiece discovery: a verified pre-existing `flows:` drift bug that reframed
FR-ED-10 and produced FR-ED-15.*

*v0.3 — Post-CRP (R1) hardening. All 8 F-suggestions ACCEPTED (dispositions in Appendix A). FR-ED-2/4
filter-grammar corrected (R1-S7: static equality WHERE, not the `filters:` facet grammar); FR-ED-9
gained per-row resolver-exception guarding (R1-F5) + first-class omitted mode (R1-F7, closing OQ-10);
FR-ED-10 gained renderer-entry + orphan-editor rules (R1-F1/F2); **FR-ED-11 corrected — the skip-hook
`$0` claim was false as written** (R1-S2, empirically verified); FR-ED-12 pinned the comparand to the
submitted mirror + newline normalization (R1-F3/F8); FR-ED-14 gained field-level write scope (R1-F4);
§3 made the 404-not-403 posture explicit (R1-F6). **FR-ED-16 added** — the widened shared prerequisite
(fix views.yaml-derived drift + skip-hook recognition across forms + flows + editors), with FR-ED-15 as
its flows slice. Net: the `$0` value proposition now rests on a fix that ALSO repairs shipped `forms:`
apps.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Both `fastapi-editor` + `editor-form` must have a `_forms_renderers()` entry; template must be header-bearing | R1 | Merged into FR-ED-10 (renderer-entry clause). | 2026-06-12 |
| R1-F2 | Orphan-editor lookup-miss → deterministic `tampered`, not crash | R1 | Merged into FR-ED-10 (orphan clause). Paired with R1-S6. | 2026-06-12 |
| R1-F3 | Dirty-detection comparand = submitted mirror; POST never recomputes resolver | R1 | Merged into FR-ED-12 (TOCTOU clause). | 2026-06-12 |
| R1-F4 | Field-level write scope (only `item-{id}`, ignore `item-{id}-<col>`) | R1 | Merged into FR-ED-14. Paired with R1-S4. | 2026-06-12 |
| R1-F5 | Resolver request-time exception → degrade per-row, not 500 | R1 | Merged into FR-ED-9 (per-row guard). | 2026-06-12 |
| R1-F6 | State 404-not-403 GET posture explicitly (no-tenancy inheritance) | R1 | Merged into §3 Non-Requirements (tenancy bullet). | 2026-06-12 |
| R1-F7 | Promote `default_value`-omitted to first-class normative mode | R1 | Merged into FR-ED-9 + FR-ED-12; closes OQ-10. | 2026-06-12 |
| R1-F8 | Specify whitespace/trailing-newline normalization in dirty-detection | R1 | Merged into FR-ED-12 clause (c) — normalize one trailing newline. | 2026-06-12 |
| R1-S7 | `filter` is static equality WHERE, not `filters:` facet grammar; GET/POST identical derivation | R1 (plan) | Cross-doc: merged into FR-ED-4 (filter-grammar clause). | 2026-06-12 |
| R1-S2 | Skip-hook `owned_file_in_sync` passes no `forms_text` → `$0` claim false | R1 (plan) | Cross-doc: FR-ED-11 corrected + **FR-ED-16 added** (widened shared fix per orchestrator decision). | 2026-06-12 |

**Disposition summary:** All 8 R1-F + all 8 R1-S suggestions ACCEPTED (none rejected — the reviewer
self-filtered). S-suggestions are recorded in the **plan's** Appendix A; their requirements-side echoes
(R1-S7, R1-S2) are noted here. R1-S2 was widened into FR-ED-16 per the "widen scope" orchestrator
decision so the fix also repairs shipped `forms:`/`flows:` `$0` recognition.

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-opus-4-8 (claude-opus-4-8[1m])
- **Date**: 2026-06-12 16:10:00 UTC
- **Scope**: `editors:` requirements (F-prefix). Grounded against actual `backend_codegen` source: `drift.py`, `flow_generator.py`, `_headers.py`, `cli_generate.py`, `assembler.py`, `crud_generator.py:render_main`, `view_codegen/renderers.py`. Focus-file asks answered first.

**Focus-file asks (answered before standard suggestions):**

**Ask 1 — Is the flows drift bug real, and is the editors drift path (S7) sufficient for a single-editor byte re-render?**
- **Summary answer:** Bug CONFIRMED. The editors drift path is sufficient for the router but has one under-specified failure mode (named-editor lookup miss) and a header-arity subtlety the template inherits.
- **Rationale:** `render_flow_router` stamps the router via `header_forms(..., "fastapi-flow")` (`flow_generator.py` `render_flow_router`, the `header_forms(...)` call) → the file carries `# GENERATED from` + `schema-sha256` → `is_owned_generated_file()` is True (`drift.py` `is_owned_generated_file`). In `check_drift`, `"fastapi-flow"` is in none of `_AI_KINDS`/`_PAGES_KINDS`/`_FORMS_KINDS`/`_SETTINGS_KINDS` (`drift.py` kind frozensets), so it falls to the default branch; the clean-tree schema sha matches, then `_renderers().get("fastapi-flow")` is `None` → returns `tampered`/exit 1 (`drift.py` default branch "unknown or missing startd8-artifact kind"). The CLI `--check` loop counts that as drift and `raise typer.Exit(1)` (`cli_generate.py` backend `--check` loop). Confirmed. The flow *shell* (`flow_generator.py` `render_flow_shell`, `{# startd8-artifact: flow-shell #}`) and *aggregator* (`flow_generator.py` `render_flows`, `# GENERATED — flow routers aggregator`) carry **no** `# GENERATED from` marker and **no** `schema-sha256`, so `is_owned_generated_file()` is False and the `--check` loop silently SKIPS them — exactly as §0/FR-ED-15 state.
- **Assumptions / conditions:** Editors register `"fastapi-editor"` + `"editor-form"` in BOTH `_FORMS_KINDS` and `_forms_renderers()` (`drift.py`). The editor-form template, unlike the flow shell, WILL be header-bearing if it uses `header_forms_tmpl` (it embeds `schema-sha256` — `_headers.py` `header_forms_tmpl`), so it cannot be silently skipped; it MUST resolve in `_forms_renderers()` or it false-flags `tampered`.
- **Suggested improvements:** see R1-F1, R1-F2, R1-F5.

**Ask 2 — Is the reset/dirty-detection rule (FR-ED-12) airtight against the GET/POST default-resolution race?**
- **Summary answer:** No — FR-ED-12 does not say *which* "default" the POST compares against, and a recomputed POST-time default can silently lose a real edit.
- **Rationale:** FR-ED-12(a) says "submitted value `==` its default → no write" but `default_value` is an app resolver `(child_row, session) -> str` (FR-ED-9) whose result can change between the GET render and the POST (source text edited concurrently; non-deterministic resolver). If POST recomputes the default, a value the user genuinely typed that happens to equal the *GET-time* default but differs from the *POST-time* default is mis-classified.
- **Assumptions / conditions:** The comparison must be against the **submitted `data-default` mirror** (client echoes the GET-time value back), never a POST-time recomputation.
- **Suggested improvements:** R1-F3.

**Ask 3 — Is the anti-IDOR allow-list (FR-ED-14) complete (parent route, field-level write scope)?**
- **Summary answer:** Partial. The child-set allow-list is right; field-level write scope and parent-route read authz are unstated.
- **Rationale:** FR-ED-14 re-derives the editable child set server-side (good) but says nothing about (a) restricting writes to the single `edit_field` column — a crafted `item-{id}-<otherfield>` param must be ignored, not written; (b) who may open `GET <route>` for a given parent (only a 404 path is specified, no 403). (b) is consistent with the "no tenancy" non-requirement, but should be explicit.
- **Suggested improvements:** R1-F4, R1-F6.

**Standard requirements suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | FR-ED-10 must state that BOTH `"fastapi-editor"` and `"editor-form"` are added to `_FORMS_KINDS` **and** get an entry in `_forms_renderers()` (a sibling `_editors_renderers` is fine), and that the editor-form template is header-bearing (carries `schema-sha256`) so — unlike the flow shell — it is NOT silently skipped and MUST resolve a renderer. | Reqs say "register `fastapi-editor` (router) + `editor-form` (template) as views.yaml-derived kinds" but a kind in `_FORMS_KINDS` with no `_forms_renderers()` entry returns `tampered` (the `unknown forms-configured kind` branch), reproducing the flows bug for the template. | FR-ED-10, after "the `_FORMS_KINDS`/`_check_forms_drift` model" | Unit test: editor app → `generate backend --check` exits 0; assert `embedded_artifact_kind` of the form template is `editor-form` and `_forms_renderers()` has the key. |
| R1-F2 | Risks | high | FR-ED-10 must define the **named-editor lookup-miss** behavior: when the on-disk file's `startd8-entity` slot names an editor that no longer exists in the current `views.yaml` `editors:` list (renamed/removed but file left on disk), the drift renderer must return a deterministic `tampered` (orphan) rather than KeyError/None. | The forms renderer signature is `(schema, forms, source_file, entity) -> text`; the editor renderer must look the editor up by name in `parse_editors(forms_text)`. A miss is unspecified — an unhandled lookup crashes `--check` (exit 2) instead of reporting drift (exit 1). | FR-ED-10, new sentence on orphan editors | Unit test: generate editor, delete its `editors:` entry, leave files → `--check` reports the router/template as drift (exit 1), not error (exit 2). |
| R1-F3 | Data | high | FR-ED-12 must specify the dirty-detection comparand is the **submitted `data-default` mirror** (the GET-time value echoed back by the client), explicitly NOT a POST-time recomputation of `default_value`. Add a clause: the POST never calls the resolver. | FR-ED-9's resolver `(child_row, session) -> str` can return a value that changes between GET and POST; comparing POST input against a freshly-recomputed default loses edits and can re-materialize a stale default. The focus file flags exactly this (GET/POST race, resolver-changes-between). | FR-ED-12, clause (a) | Test: resolver returns `A` at GET; mutate source so resolver would return `B`; POST input `A` (unchanged) → `edit_field` stays NULL (compared against submitted mirror `A`, not recomputed `B`). |
| R1-F4 | Security | high | FR-ED-14 must add explicit **field-level write scope**: the POST parser accepts only params matching the single-`edit_field` input-name pattern (e.g. `item-{id}`), and ignores any other form param — a crafted `item-{id}-status=…` or extra column name is never written. | FR-ED-14 covers WHICH rows (id allow-list) but not WHICH columns. Mass-assignment over columns is a distinct surface from cross-parent row access; the §3 non-requirement "exactly one `edit_field`" must be enforced at the POST boundary, not just declared. | FR-ED-14, new sentence after the id allow-list | Test: POST with `item-{valid_id}-otherCol=x` alongside the legit `item-{id}` field → only `edit_field` changes; `otherCol` untouched. |
| R1-F5 | Interfaces | medium | FR-ED-9 should specify resolver **exception behavior at request time**: if the imported resolver raises during GET pre-fill, the archetype must degrade (fall back to raw `edit_field`, log) rather than 500 the whole editor — matching the "absent → fall back" posture already stated. | FR-ED-9 defines present/absent but not present-but-raises. The `flows:` `on_finish` precedent wraps the IMPORT in `try/except` but the CALL is unguarded (`flow_generator.py` `finish_call`); editors should not inherit that gap in a per-row pre-fill loop where one bad row would blank the whole form. | FR-ED-9, after "absent → fall back to `edit_field` raw" | Test: resolver raises on one child → that child pre-fills from raw `edit_field`, form still renders all children. |
| R1-F6 | Security | low | FR-ED-14 / §3 should state explicitly that the GET route has **no read-authorization** beyond parent-existence (404 only, no 403), and that this is the deliberate inheritance of the CRUD/no-tenancy posture — so a reviewer does not mistake the missing 403 path for an oversight. | The focus file asks "who may open `<route>` for a given parent". The honest answer given the "No tenancy" non-requirement is "anyone who can reach CRUD"; making it explicit prevents a later reviewer re-filing it as a gap. | §3 Non-Requirements, extend the tenancy bullet | N/A (doc clarity); cross-check against the `deployment-mode` Tier B reference already cited. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F7 | Validation | medium | OQ-10 (`default_value`-omitted mode) should be promoted to a normative line in FR-ED-9: when omitted, the GET emits the `data-default` mirror from the raw `edit_field` value (empty string for NULL), so FR-ED-12 dirty-detection still has a comparand. | FR-ED-12 depends on a `data-default` existing for EVERY input; the omitted-resolver path must still populate it deterministically, else the zero-seam mode has no defined default mirror and every unchanged NULL row could re-materialize. Cross-requirement interaction (FR-ED-9 ↔ FR-ED-12). | FR-ED-9 (resolver-absent) + FR-ED-12 | Test: editor with no `default_value`, child with NULL `edit_field` → input renders `data-default=""`; POST unchanged-empty → stays NULL (not written). |
| R1-F8 | Data | low | FR-ED-6/FR-ED-12 should address **whitespace-only differences**: state whether the submitted value is compared to its default byte-exact or after normalizing a trailing newline. A `<textarea>` commonly appends a newline; byte-exact comparison then writes a near-identical value, defeating "store only if changed". | The focus file lists "whitespace-only differences" as a dirty-detection edge. Without a stated normalization rule the comparison is ambiguous and likely over-writes. | FR-ED-12, clause (c) | Test: default `"x"`, POST `"x\n"` → assert the chosen rule (recommend: normalize trailing newline) holds and does not spuriously write. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — R1 is the first round)

**Disagreements** (untriaged prior suggestions this reviewer would reject):
- (none — R1 is the first round)
