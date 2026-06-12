# `editors:` Archetype — Implementation Plan

**Version:** 1.1 (Post-CRP R1)
**Date:** 2026-06-12
**Tracks:** `EDITORS_ARCHETYPE_REQUIREMENTS.md` (v0.3 — planning reflection + CRP R1)
**Status:** Planned (pre-implementation; CRP R1 triaged)

> This plan was written by reading the actual `backend_codegen` machinery the archetype must slot into.
> The discoveries (§A) fed the v0.2 self-reflective update of the requirements. **One discovery is a
> verified, pre-existing bug in the `flows:` feature** that this work should fix in passing.

---

## A. Discoveries (planning vs. the v0.1 assumptions)

| v0.1 / brief assumed | Planning revealed (grounded in code) | Impact |
|----------------------|--------------------------------------|--------|
| "Follow the `flows:` precedent and editor files will be `$0`/drift-clean" (FR-ED-10) | **VERIFIED BUG:** `fastapi-flow` is registered in **no** drift renderer map (`drift.py` `_AI/_PAGES/_FORMS/_SETTINGS_KINDS` + `_renderers()`). The flow **router** carries `header_forms` (→ `# GENERATED from` + `schema-sha256`), so `is_owned_generated_file()` = True, drift runs, hits the default path, `_renderers().get("fastapi-flow")` → `None` → **`tampered`**. Confirmed empirically: `generate backend --check` on a `flows:`-using app exits **1** on a clean tree. Shell + aggregator carry no `# GENERATED from`/sha header → silently skipped (also unprotected). | FR-ED-10 cannot "copy flows." Editors **must** register a drift path (the `_FORMS_KINDS`/`_check_forms_drift` model). **New plan step S7.** Also a free **quick win**: register `fastapi-flow` while we're in `drift.py` (S12). |
| `default_value: app.resume_wizard:effective_text` (`module:fn`) (FR-ED-9, OQ-1) | `flows:` `on_finish` is a **bare fn name** imported from a **fixed conventional module** (`flow_generator.py:45` → `from app.flows.finishers import <name>`). Two seam syntaxes in one manifest is avoidable inconsistency, and `module:fn` is unvalidatable at render (arbitrary dotted path). | OQ-1 → adopt the fixed-module convention: `default_value: <bare_fn>` resolved from `app/editors/resolvers.py`. Simpler, consistent, validatable-by-shape. **Updates FR-ED-9.** |
| Pre-fill from effective text **and** "empty → NULL = reset" (FR-ED-4/6, OQ-2) | These collide. If a child with `overrideText IS NULL` is pre-filled with its **source** text and saved unchanged, the POST writes source text into `overrideText` — **materializing a default into an override**, so the field stops tracking the source and reset is defeated. | OQ-2 → require **dirty-detection**: render each input with a `data-default` (the resolved effective value) and on POST **store only inputs that differ from their submitted default; unchanged → leave/!set NULL**. **Updates FR-ED-5/6; new FR-ED-12.** This is the gating correctness decision. |
| Bulk write is "an increment on CRUD" (cheap) | True for the read side (the parent-scoped query already exists: `view_codegen/renderers.py:63,126,166` → `select(Child).where(Child.fk == parent.id).order_by(...)`), but the **bulk multi-row write** is genuinely net-new — CRUD `POST` handlers are single-row (`htmx_generator.py:738/779`). One transaction over N rows + per-row dirty/reset logic is the real new code. | Confirms scope: ~1 new generator module (~router + template), reusing query/filter/POST-parse idioms. Manageable. |
| Mount is free (FR-ED-8) | `main.py` mounts aggregators via **dedicated tolerant blocks** in `render_main` (`crud_generator.py:260-295`), each added when its feature shipped (flows added its own block). `main.py` is always-generated + drift-tracked. | OQ-4 → editors add **one** tolerant block to `render_main` → a **one-time `main.py` byte change (drift) for every existing app** on first regen. Precedented (flows did the same), acceptable, but must be called out. **New FR-ED-13.** |
| (not considered) Mass-assignment (OQ-5) | The bulk POST will receive child ids from the form. Trusting them lets a user edit children of a **different** parent (IDOR) or non-`included` rows. | OQ-5 → the handler must re-derive the editable child set **server-side** (`WHERE fk == parent.id AND filter`) and accept writes **only** for ids in that set; ignore unknown ids. **New FR-ED-14.** No worse than CRUD, but the N-row surface makes it worth enforcing in the archetype. |
| (not considered) Route namespacing (OQ-8) | CRUD owns `/ui/*`, flows own `/flow/*`. Editor `route` is author-supplied free-form (`/resume-wizard/{id}/edit`). Nothing stops a collision with a `views:` route (also free-form) or a future CRUD path. | OQ-8 → validate the route contains exactly one `{id}` placeholder and (cheap) warn on a literal `/ui/`-prefix collision; full cross-section route-uniqueness is a nicety. **Updates FR-ED-2 validation.** |
| Header machinery is enough | `header_forms` (schema+views two-hash) + `header_forms_tmpl` already exist (`_headers.py:115/138`) and the editor name can ride the **`startd8-entity:` header slot** (`embedded_entity()` recovers it in drift). | No new header builder needed — reuse `header_forms`/`header_forms_tmpl` with a new `kind` and the editor name in the entity slot. Enables single-editor drift re-render. |

**Heuristic check:** 6 of 14 requirements changed/added from planning (>30%). The brief was a good
generic shape but under-specified on **idempotency, reset semantics, and security** — exactly where the
deterministic-codegen invariants live.

## B. Architecture & file plan

New module `src/startd8/backend_codegen/editors_manifest.py` (parse, mirror `flows_manifest.py`) and
`src/startd8/backend_codegen/editor_generator.py` (render, mirror `flow_generator.py`).

| Step | File(s) | What | FR |
|------|---------|------|----|
| **S1** | `editors_manifest.py` (new) | `EditorSpec` dataclass + `parse_editors(views_text, known_entities)`; strict keys, dup-name guard, tolerant absence. | FR-ED-1/2 |
| **S2** | `editor_generator.py` (new) | `_validate_editor(schema, spec)` — entity/fk/edit_field/group_by/order_by/filter-key checks (reuse `filters_manifest` + `parse_prisma_schema`); route `{id}` shape + collision warn. | FR-ED-3, OQ-8 |
| **S3** | `editor_generator.py` | `render_editor_router(schema, views, spec)` → `app/editors/<name>.py`. **GET:** parent 404; `select(child).where(fk==id).where(<filter-equality>).order_by(order_by)`; group; pre-fill via tolerant resolver import seam with a **per-row try/except** (resolver raises → that row falls back to raw `edit_field`, form still renders — R1-F5); each input carries a `data-default` mirror (resolver result, or raw `edit_field`/`""` in omitted mode — R1-F7). **POST:** parse **only** params matching the `item-{id}` name pattern, ignore all others incl. `item-{id}-<col>` (field-level write scope — R1-F4/R1-S4); re-derive the editable set with the **identical** `where(fk==id).where(<filter>)` expression as GET (R1-S7); dirty-detect against the **submitted mirror** (never recompute the resolver — R1-F3), normalize one trailing newline (R1-F8); reset→NULL; one txn; PRG. Uses `header_forms(..., "fastapi-editor")`. | FR-ED-4/5/6/9/12/14 |
| **S4** | `editor_generator.py` | `render_editor_form(views, spec)` → `app/templates/editors/<name>/form.html`: grouped `<section>`s or flat list; one `<textarea name="item-{id}">` per child with `data-default`. Uses `header_forms_tmpl(..., "editor-form", entity=name)`. | FR-ED-7/12 |
| **S5** | `editor_generator.py` | `render_editors(schema, views)` → list of (path, text) incl. `app/editors/__init__.py` aggregator (`editor_routers`), **with a real `# GENERATED from`/sha header** (avoid the flow-aggregator gap). Empty when no `editors:`. | FR-ED-8 |
| **S6** | `assembler.py:80` | `out.extend(render_editors(schema_text, views_text or ""))` right after `render_flows`. | FR-ED-8/10 |
| **S7** | `drift.py` | Add `"fastapi-editor"` (router) + `"editor-form"` (template) to the **forms** drift kind-set so `check_drift` routes them with `forms_text`; add a **renderer entry for EACH** in `_forms_renderers()`/sibling `_editors_renderers()` (a kind in the set without a renderer → `tampered`, R1-F1) that re-renders the **named** editor via `parse_editors(forms_text)` keyed off `embedded_entity()`. **Orphan editor** (name absent from current `views.yaml`) → return deterministic `tampered`, never `KeyError`/exit 2 (R1-F2/R1-S6). The `editor-form` template MUST carry a `schema-sha256` header (header-bearing) so it is verified, not silently skipped. | FR-ED-10 |
| **S8** | `crud_generator.py` `render_main` | Add **one static-literal** tolerant `try: from .editors import editor_routers / except ModuleNotFoundError: editor_routers = []` block + mount loop, after the flows block. **Unconditional** — `render_main` is the schema-only `fastapi-main` artifact (no `views.yaml` at re-render), so the block must be byte-identical whether or not `editors:` is declared; inertness comes from `editor_routers = []`, never from omitting the block (R1-S5). | FR-ED-8/13 |
| **S9** | `provider.py` / entry points | Register editor kinds as owned. **NOTE (R1-S2):** `is_owned_generated_file` covers header-bearing files, but the `$0` skip-hook `owned_file_in_sync` does **not** confirm in-sync for any views.yaml-derived kind today (passes no `forms_text`). Editor `$0` recognition depends on **S13**, not on this step alone. | FR-ED-11 |
| **S10** | `cli_generate.py` | No new flag — `editors:` rides the existing `views_text` already threaded to generate **and** `--check` (`forms_text=views_text`, line 288). Confirm pass-through. *(This is why `--check`/FR-ED-10 works without S13; only the prime-contractor skip-hook/FR-ED-11 needs S13.)* | FR-ED-10 |
| **S11** | `tests/unit/backend_codegen/test_editors.py` (new) | Parse (strict/tolerant/dup), validation (bad fk/field/entity, route `{id}` shape, `/ui/` collision warn), render snapshot, **`--check` in_sync round-trip**, dirty-detect (mirror-comparand, trailing-newline, NULL-stays-NULL), reset, **IDOR row + column allow-list** (`item-{id}-<col>` ignored), resolver present/absent/**raises**, orphan-editor → exit 1, mount-block byte-identical with/without `editors:`. | all |
| **S12** | `drift.py` + `flow_generator.py` (FR-ED-15) | **Two halves (R1-S1/R1-S3, both load-bearing):** (1) register `fastapi-flow` in the **forms** path (`_FORMS_KINDS` + `_forms_renderers()` entry re-rendered WITH `forms_text` via `render_flow_router` — NOT the schema-only `_renderers()`, which re-buries the bug); (2) give the flow **shell + aggregator** real `# GENERATED from`/`schema-sha256` headers so they are drift-protected, not silent-skipped. Regression test: clean `flows:` app → `--check` exit 0, and tampering the shell now reports drift. **Independently shippable.** | FR-ED-15 |
| **S13** | `drift.py` skip-hook (FR-ED-16, **shared prerequisite**) | Thread `views.yaml` into `owned_file_in_sync` (and other skip-hook callers) so `_check_forms_drift` receives `forms_text` instead of `None`. Fixes `$0` recognition for **all** views.yaml-derived kinds — `fastapi-web-forms`, `htmx-created` (broken today), `fastapi-flow`, `fastapi-editor`, `editor-form`. Regression suite asserts `owned_file_in_sync` returns True for in-sync instances of each (incl. the shipped forms kinds). **Blocks FR-ED-11; also repairs shipped `forms:`/`flows:` apps.** | FR-ED-11/16 |

## C. Risks & validation

- **R1 — Drift round-trip is the gate.** The single most important test (S11) is generate→`--check`==`in_sync`
  with an `editors:` section present. If S7 is wrong, we reproduce the flows bug. Validate by mirroring
  the empirical check used to find it.
- **R2 — `main.py` one-time drift (FR-ED-13).** Document that the first `generate backend` after this
  ships re-stamps `main.py` for every app. Verify the block is inert (`editor_routers = []`) when no
  `editors:` declared, so behavior is identical for non-editor apps.
- **R3 — Dirty-detection semantics (FR-ED-12).** The correctness crux. Test: child with NULL override,
  pre-filled with source, saved unchanged → `edit_field` stays NULL (not materialized). Child edited →
  stored. Child cleared → NULL.
- **R4 — Resolver contract.** Test the tolerant seam three ways: resolver present (used), absent (falls
  back to raw `edit_field`), and **present-but-raises** (per-row degrade, form still renders — R1-F5).
- **R5 — Skip-hook `$0` recognition (CRP R1-S2, verified).** `owned_file_in_sync` passes no `forms_text`,
  so views.yaml-derived files (editors AND shipped `fastapi-web-forms`/`htmx-created`) return `False`
  today → fall through to the LLM, defeating the `$0` claim. **S13** is the fix and a prerequisite for
  FR-ED-11. Validate: `owned_file_in_sync` returns True for an in-sync editor router AND a `fastapi-web-forms`
  `web.py` after S13. **Distinct from R1:** `--check`/FR-ED-10 already threads `forms_text` (S10) and works
  without S13; only the prime-contractor skip-hook is broken.

## D. Sequencing

**S13 (skip-hook fix, FR-ED-16) and S12 (flows drift, FR-ED-15) are the shared-prerequisite slice — ship
them first as one or two small PRs.** They de-risk the drift/skip machinery the archetype reuses and
**immediately repair shipped `forms:`/`flows:` apps** (a `$0`-recognition + `--check` fix that exists
independent of editors). Then S1→S6 (manifest+generation), S7+S8 (editor drift + mount), S9/S10 (wiring),
S11 (tests). The archetype proper is ~2 new modules + ~4 touched files; S12/S13 touch only `drift.py`
(+ `flow_generator.py` headers).

> **Release note (R1-S8):** S12 changes the drift behavior of **every existing `flows:` app** — after it
> ships, those apps correctly report `--check` in_sync, but the first regen also re-stamps the
> previously-headerless shell/aggregator (a one-time byte change, analogous to FR-ED-13's `main.py`
> re-stamp). Call it out so it is not mistaken for unexpected drift.

---

*Plan v1.0 — feeds the v0.2 self-reflective requirements update (§0 Planning Insights).*
*Plan v1.1 — Post-CRP (R1). All 8 S-suggestions ACCEPTED: S3 gained field-level scope + mirror-comparand
+ per-row resolver guard (R1-S4/S7/F-cross); S7 gained renderer-entry + orphan rules (R1-F1/F2/S6); S8
made the mount block a static literal (R1-S5); S12 split into two load-bearing halves (R1-S1/S3); **S13
added** for the widened skip-hook fix (R1-S2 → FR-ED-16); R5 risk + S8 release note added (R1-S8).
Dispositions in Appendix A; the R1 coverage matrix is preserved as-is with a post-triage status note
below it (every Partial/Missing gap now Addressed).*

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
| R1-S1 | S12 router fix must use the FORMS path (re-render WITH `forms_text`), not schema-only `_renderers()` | R1 | Merged into S12 (half 1). | 2026-06-12 |
| R1-S2 | `owned_file_in_sync` passes no `forms_text` → `$0` claim false for all views.yaml-derived kinds | R1 | **Added S13** + Risk R5; corrected S9; widened to FR-ED-16. | 2026-06-12 |
| R1-S3 | S12 shell/aggregator header fix is load-bearing, not parenthetical | R1 | Merged into S12 (half 2). | 2026-06-12 |
| R1-S4 | Field-level write scope (only `item-{id}`) at the POST parser | R1 | Merged into S3. Paired with R1-F4. | 2026-06-12 |
| R1-S5 | Mount block must be a static literal, byte-identical with/without `editors:` | R1 | Merged into S8 + Risk R2. | 2026-06-12 |
| R1-S6 | Editor drift renderer resolves by name; orphan-editor → `tampered` not crash | R1 | Merged into S7. Paired with R1-F2. | 2026-06-12 |
| R1-S7 | Pin input-name scheme; GET/POST identical derivation; `filter`=equality WHERE not facet grammar | R1 | Merged into S3; requirements echo in FR-ED-4. | 2026-06-12 |
| R1-S8 | Sequencing note: S12 re-stamps existing `flows:` apps (one-time byte change) | R1 | Merged into §D release note. | 2026-06-12 |

**Disposition summary:** All 8 R1-S ACCEPTED (none rejected). R1-S2 was widened into a dedicated step
(S13) + requirement (FR-ED-16) per the orchestrator's "widen scope" decision, so the skip-hook fix also
repairs shipped `forms:`/`flows:` `$0` recognition. The 8 R1-F (requirements) dispositions are recorded
in the **requirements** doc's Appendix A.

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-opus-4-8 (claude-opus-4-8[1m])
- **Date**: 2026-06-12 16:12:00 UTC
- **Scope**: `editors:` implementation plan (S-prefix), grounded against `drift.py`, `flow_generator.py`, `_headers.py`, `cli_generate.py`, `assembler.py`, `crud_generator.py`. Drift round-trip + skip-hook focus per the sponsor file.

**Executive summary (top risks / gaps):**
- Flows drift bug CONFIRMED at the byte level (S12 premise is sound) — but S12's *router* fix must go through the **forms** drift path (it carries `header_forms`/`forms-sha`), NOT the default `_renderers()` map; getting this wrong re-buries the bug.
- **S9/FR-ED-11 claim is FALSE as written**: `owned_file_in_sync(schema_text, ondisk_text)` passes **no `forms_text`**, so any `_FORMS_KINDS` file (incl. editors AND today's `fastapi-web-forms`/`htmx-created`) routes to `_check_forms_drift` with `forms_text=None` → `ERROR` → returns False. The skip-hook cannot currently confirm a views.yaml-derived file as in-sync. This is a pre-existing skip-hook limitation the plan inherits and must address.
- S7 editor renderer needs the parsed editor spec via name lookup; orphan-editor (file present, manifest entry gone) behavior is undefined → risks `--check` exit 2.
- S3 omits field-level write scope (mass-assignment over columns) — the id allow-list alone is insufficient.
- S8 mount block: `render_main` is `fastapi-main` (schema-only default path); the editor block must be byte-deterministic regardless of `editors:` presence or it desyncs from the schema-only re-render.

**Plan suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Risks | critical | S12 must specify that `fastapi-flow` is registered in the **forms** drift path (`_FORMS_KINDS` + `_forms_renderers()` with a `(schema, forms, source_file, entity) -> render_flow_router(...)` entry), NOT the default `_renderers()` map — because the flow router header is built by `header_forms(..., "fastapi-flow")`, so it carries a `forms-sha256` and must be re-rendered WITH `forms_text`. Registering it in the schema-only `_renderers()` would re-render without views.yaml and false-flag tampered. | `flow_generator.py` `render_flow_router` calls `header_forms(...)`; `_check_forms_drift` requires `forms_text`. A naive "add `fastapi-flow` to `_renderers()`" reading of S12 would not pass `forms_text` and re-buries the bug differently. | §B Step S12 | Regression test: clean `flows:` app → `generate backend --check --views views.yaml` exits 0; assert flow router routes through `_check_forms_drift`. |
| R1-S2 | Architecture | high | S9 must NOT claim `owned_file_in_sync` returns True for in-sync editor files "automatically". As written, `owned_file_in_sync(schema_text, ondisk_text)` (`drift.py`) calls `check_drift` with `forms_text` unset → `_FORMS_KINDS` files hit `_check_forms_drift` with `forms_text=None` → `DriftResult("error", ERROR)` → returns False. Either (a) the skip-hook signature must thread `forms_text`, or (b) editors must be recognized owned by a different mechanism. Verify the SAME limitation already affects `fastapi-web-forms`/`htmx-created`. | This is the load-bearing skip-hook contract for `$0.00`-owned recognition (FR-ED-11). The plan asserts it works for free; the code shows it cannot for any views.yaml-derived kind without a signature change. | §B Step S9 + §C new risk R5 | Test: generate editor, call `owned_file_in_sync(schema_text, router_text)` → currently False; assert the fix returns True (and that `fastapi-web-forms` does too). |
| R1-S3 | Risks | high | S12's parenthetical "(+ give the flow shell/aggregator real headers)" is load-bearing, not optional — promote it to an explicit sub-step. Without `# GENERATED from` + `schema-sha256` on the shell/aggregator they remain `is_owned_generated_file()`=False and are silently skipped by the `--check` loop (`cli_generate.py`), i.e. unprotected, not merely untested. | A reader could ship S12 as "register `fastapi-flow`" only and leave the shell/aggregator silent-skip. The bug has two halves (router false-flag + shell/aggregator silent-skip); S12 must fix both. | §B Step S12 | Test: tamper the flow shell after generate → `--check` now reports drift (currently it does not). |
| R1-S4 | Security | high | S3 must add **field-level write scope** to the POST handler: parse only form params matching the single-`edit_field` input-name pattern (e.g. `item-{id}`), ignore all others. The server-side id allow-list (OQ-5/FR-ED-14) bounds WHICH rows; this bounds WHICH columns. | S3 lists "server-side id allow-list" but not column scoping. A crafted `item-{id}-<col>` could write a second column if the parser is permissive. Pairs with R1-F4 in the requirements doc. | §B Step S3 (POST sub-clause) | Test in S11: POST a legit `item-{id}` plus `item-{id}-otherCol` → only `edit_field` changes. |
| R1-S5 | Validation | high | S8/R2 must assert the editor mount block is **byte-identical whether or not `editors:` is declared**. `render_main` is the `fastapi-main` artifact (schema-only default `_renderers()` path — it does NOT receive views.yaml), so the block must be a static literal like the flows block (`crud_generator.py` `render_main`, the unconditional `from .editors import editor_routers` try/except), never conditioned on the manifest, or `main.py` desyncs from its schema-only re-render. | The flows precedent embeds the block unconditionally; FR-ED-13's "inert when absent" is achieved by `editor_routers = []` on `ModuleNotFoundError`, NOT by omitting the block. If S8 conditions the block on `editors:` presence, drift re-render (schema-only) and generate (manifest-aware) diverge. | §B Step S8 + §C Risk R2 | Test: generate two apps (one with `editors:`, one without) → `main.py` byte-identical; both `--check` in_sync. |
| R1-S6 | Interfaces | medium | S7 must specify the editor drift renderer recovers the editor **by name** from `parse_editors(forms_text)` using the `startd8-entity` slot, and define the lookup-miss (orphan editor) result as `tampered`, not an exception. | The `_forms_renderers()` entry receives `(schema, forms, source_file, entity)`; the editor name is in `entity`. If the editor was removed from views.yaml but the file remains, the lookup must degrade to drift (exit 1), not crash `--check` (exit 2). Mirrors R1-F2. | §B Step S7 | Test: remove an editor from views.yaml, leave files → `--check` exit 1 (drift), not 2 (error). |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Data | medium | S3/S4 should pin the input `name` scheme and reconcile it with the parent-scoped query. The read query (`select(child).where(fk==id).where(filter).order_by(order_by)`) and the POST id allow-list must use the SAME `WHERE fk==parent.id AND filter` derivation; document that `filter` is the static manifest filter (`filters_manifest.EntityFilter`-style own-column semantics), so a row excluded by `filter` is neither rendered (GET) nor writable (POST). | The reuse claim leans on `view_codegen` parent-scoped query + `filters_manifest`; the GET and POST must derive the identical set or a row visible-but-not-writable (or vice versa) appears. `filters_manifest.parse_filters` is `{facets, search}` only — confirm the editor `filter: {included: true}` maps to an equality WHERE, not a facet UI. | §B Steps S3/S4 | Test: child excluded by `filter` → absent from GET form AND ignored if its id is POSTed. |
| R1-S8 | Ops | low | §D Sequencing should note S12 (flows drift fix) changes the drift behavior of EVERY existing `flows:` app: after S12 ships, those apps will (correctly) report `--check` in_sync, but the first regen also re-stamps the shell/aggregator with new headers — a one-time byte change for existing flows apps, analogous to FR-ED-13's `main.py` re-stamp. Call it out so it is not mistaken for unexpected drift. | S12 is "independently shippable" but adding headers to previously-headerless shell/aggregator files changes their bytes; downstream `flows:` apps see a one-time diff on first regen after S12. | §D Sequencing | N/A (release note); covered by the S12 regression test asserting post-regen `--check` in_sync. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — R1 is the first round)

**Disagreements** (untriaged prior suggestions this reviewer would reject):
- (none — R1 is the first round)

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to the plan step(s) that implement it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-ED-1 (`editors:` section, strict/tolerant) | S1 | Full | — |
| FR-ED-2 (grammar + route `{id}`/`/ui/` validation) | S1, S2 | Full | — |
| FR-ED-3 (contract validation, loud at render) | S2 | Full | — |
| FR-ED-4 (GET route, parent 404, scoped query, pre-fill) | S3 | Partial | Resolver-raises-at-request degradation unspecified (R1-F5); orphan/empty-section handling not mentioned. |
| FR-ED-5 (POST save, one txn, PRG) | S3 | Full | — |
| FR-ED-6 (reset-to-default → NULL) | S3 | Partial | Whitespace/trailing-newline normalization unspecified (R1-F8). |
| FR-ED-7 (template, grouped/flat, provenance header) | S4 | Full | — |
| FR-ED-8 (mount: per-editor router + aggregator) | S5, S6, S8 | Full | — |
| FR-ED-9 (`default_value` resolver seam, fixed module) | S3 | Partial | Request-time exception behavior (R1-F5); `default_value`-omitted normative path (R1-F7). |
| FR-ED-10 (`$0`, idempotent, drift-clean editors path) | S7 | Partial | `editor-form` template MUST resolve in `_forms_renderers()` (R1-F1/R1-S6); orphan-editor lookup-miss result undefined (R1-F2/R1-S6). |
| FR-ED-11 (provider owned-kinds; `owned_file_in_sync`) | S9 | Partial | **Claim is false as written** — `owned_file_in_sync` passes no `forms_text` → `_FORMS_KINDS` files return ERROR/False (R1-S2). Needs a skip-hook signature fix. |
| FR-ED-12 (dirty-detection) | S3, S4 | Partial | Comparand (submitted mirror vs POST-recompute) unspecified (R1-F3); whitespace normalization (R1-F8); omitted-resolver default mirror (R1-F7). |
| FR-ED-13 (one-time `main.py` re-stamp, inert when absent) | S8 | Partial | Must assert block is byte-identical with/without `editors:` since `render_main` is schema-only (R1-S5). |
| FR-ED-14 (server-side allow-list, anti-IDOR) | S3 | Partial | Field-level write scope (column mass-assignment) not covered (R1-F4/R1-S4); GET read-authz posture (403 vs 404) not stated (R1-F6). |
| FR-ED-15 (quick win: fix `flows:` drift, shippable) | S12 | Partial | Router fix must use the FORMS path not the default `_renderers()` (R1-S1); shell/aggregator header fix is load-bearing, not parenthetical (R1-S3). |
| OQ-9 (emit resolver stub?) | (none) | Missing | Deferred to CRP per reqs §4; no plan step — acceptable as an open question, but no step reserves the decision. |
| OQ-10 (`default_value` optional) | (none) | Missing | Plan does not carry the zero-seam mode; promote per R1-F7 since FR-ED-12 depends on a default mirror existing for every input. |

> **Post-triage status (orchestrator, after R1 — the matrix above is the preserved R1 snapshot):** every
> "Partial"/"Missing" gap is now **Addressed** in plan v1.1 + requirements v0.3 — FR-ED-4/9 (R1-F5/F7) in
> S3; FR-ED-10 (R1-F1/F2) in S7; **FR-ED-11 (R1-S2) in the new S13** (+ FR-ED-16); FR-ED-12 (R1-F3/F8) in
> S3; FR-ED-13 (R1-S5) in S8; FR-ED-14 (R1-F4/F6) in S3 + §3; FR-ED-15 (R1-S1/S3) in S12; OQ-10 closed
> (zero-seam mode now first-class in FR-ED-9). OQ-9 remains open (resolver-stub decision). New work items
> from triage: **S13** (skip-hook fix) and the **FR-ED-16** widening.
