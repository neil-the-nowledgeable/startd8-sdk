# FK Pickers on Generated Create/Edit Forms — Requirements

**Project:** startd8-sdk (python-contract-codegen)   **Criticality:** medium
**Version:** 0.5 (post-CRP R2)
**Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** startd8-python-cascade
**Pairs with:** `FK_PICKER_PLAN.md`
**Inherits standards:** det-req-kit
**Audience:** end-user
**Trust boundary:** the browser form body is untrusted — an FK id arriving in a POST is a claim, not a fact; trust stops at `create_<e>` / `update_<e>`, where the id must be resolved against the DB and, when the app is tenant-scoped, against the principal's own rows before it is written.
**Data classification:** internal — generated app data; option *labels* are row content, so the options query inherits the app's row-visibility rules.

> **Companions** (cite, do not restate)
>
> - `_PILOT_2026-08-14_onboarding-household.md` — **P1-2** is the motivating defect ("FK fields are
>   raw text IDs (`assigneeId`, `memberId`, …); picker is later enhancement"); **P0-3 / P0-4** are the
>   unvalidated-write failure class this must not reopen.
> - `FORM_FIELD_LAYOUT_FR-FH-11.md` — the label → instruction → control → error stacking the picker obeys.
> - `FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md` — the PRG / `?created=` contract the picker must not disturb.
> - `EDITORS_ARCHETYPE_REQUIREMENTS.md` — the **promotion-door precedent** (an affordance becomes a
>   declared archetype only once proven), and its `FR-ED-16`, the manifest-derived drift/skip-hook trap
>   this requirement is deliberately shaped to avoid.
> - `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` — the REQ whose non-goals deferred full FK picker widgets.
>   This document is that deferred item, not an extension of that archetype.
>
> **Id convention:** FRs are numbered `FR-1…FR-10` for det-req extraction; in code comments and
> cross-doc citation they carry the `FR-FK-n` alias, matching how `FORM_SUBMIT_BEHAVIOR`'s `FR-n`
> appear as `FR-FS-n` in `htmx_generator.py`.

---

## 0. Planning Insights (Self-Reflective Update)

> v0.1 assumed this was a **widget change**: teach `_field_kind` to recognize `*Id` fields and emit a
> `<select>`. Planning against the real generator falsified that at three levels — the *trigger* is
> wrong (name suffix ≠ relation), the *options* cannot live in the template at all (enum options are
> baked at generate time; FK rows are runtime data, so four separate routes must supply them), and
> the *validation* path has no seam for a non-enumerable allowed-set. Planning also found the FK
> target resolver **already exists** and is authoritative, which removed the largest v0.1 work item.
> 10 corrections; scope moved from "one function" to "one resolver + four call sites + two guards",
> while the total *new machinery* went **down** (no new manifest, no new drift dep-set).

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| A new relation resolver / parser extension is needed to map `assigneeId` → `Member`. | It already exists and is authoritative: `sqlmodel_renderer._fk_map()` (L144–171) parses `@relation(fields:[…], references:[…])`, and the generated `tables.py` already emits `foreign_key="member.id"`. It returns the *table* name (`f.type.lower()`), not the model class the picker must query. | Largest v0.1 item deleted. **FR-2** promotes one shared resolver returning the **model name** + ref column, and re-expresses `_fk_map` on it (single source, not a fork). |
| An FK field can be recognized by its `*Id` name suffix — `_structural_hint` (L614) already does exactly that. | The suffix is **wrong**. `DueInstance.sourceId` (household `schema.prisma` L196–208) is documented as *"a loose reference … (no ORM FK — polymorphic by sourceType)"*. A suffix-driven picker would render a select over a target that does not exist. | **FR-1** triggers on the `@relation` attribute only. `sourceId` staying a text input is a named **Verify**, not an accident. |
| Adding `<select>` to `form.html` is the whole rendering change (enums do it that way). | Enum options are **baked into the template at generate time** (L709–742). FK options are **runtime rows** and cannot be. The template must iterate a context variable, and **every** route rendering `form.html` must supply it: `new_<e>` (L1129), the `create_<e>` error re-render (L1160), `edit_<e>` (L1189), the `update_<e>` error re-render (L1208). | Biggest scope correction. **FR-3** requires **one** options helper called by all **four** sites; a missed site is a silently-empty picker on the error path — a context-arrival failure. |
| `_{e}_allowed` can carry the valid FK ids, the way it carries enum values. | `_{e}_allowed` is a **generate-time frozenset** (L1088–1092); an FK's valid set is unknowable at generate time. Today a forged `assigneeId` passes `_form_errors` untouched and dies as an `IntegrityError` → 500 — the same class as pilot **P0-3 / P0-4**. | **FR-7** adds a **runtime existence check** via a separate generated `_{e}_fk` map; `_{e}_allowed` semantics are unchanged. |
| Reading options is a read of already-visible data, so tenancy is unaffected. | False, and it is a **new** leak. Every DB-touching handler is owner-scoped (`owner_field == principal.id`, L1100–1117, FR-TEN-2). A naive `select(Member)` for options would put **other tenants' row labels and ids** in the dropdown — a surface that previously exposed neither. | **FR-8** scopes the options query *and* the existence check with the same `owner_field`, preserving the 404-not-403 posture (never leak existence). |
| The option label needs a new `pickers:` manifest to say which column to show. | It needs no config at all: `_default_label_field` + `_LABEL_HEURISTIC = ("name","title","label","headline")` (L392–398) already exist for the row view-link, and are already the zero-config answer to "what does a row read as". | **FR-4** reuses the heuristic. The `display.yaml` `label_field` **override** is deferred to a Non-goal with a grounded reason: it would add a display hash to `web.py`, which today has none. |
| A `pickers:` manifest is the natural way to make this opt-in. | It would be the expensive way. `htmx-form` sits in `drift._HUMAN_INPUTS_KINDS` (L101) as a schema+human_inputs 2-hash kind; a new input changes its dep-set and must be threaded through `owned_file_in_sync` / `check_drift` / `assembler` / `cli_generate` / the skip-hook — exactly the breakage `FR-ED-16` records. | **FR-10**: derive from the schema alone. **No new manifest, no new CLI flag, no new drift dep-set.** Machinery went down, not up. |
| Pre-selecting a parent from a link (`?assigneeId=…`) is a new requirement. | Already wired: `new_<e>` prefills any query param whose key is in `_{e}_rules` (L1131–1133). | **FR-6** narrows to "honor the existing prefill precedence" (prefill → current item → default), reusing the enum select's precedence expression (L716–734). No new mechanism. |
| The widget kind and the coercion kind are the same thing, so `_field_kind` should return `"fk"`. | They diverge here for the first time. `_field_kind` feeds **both** the template widget *and* `_{e}_rules`, which drives the shared `_coerce` / `_field_error` helpers in `_WEB_HELPERS` — helpers every generated app already depends on. Returning `"fk"` would force a branch into both. | **FR-1 / FR-7**: a separate `is_fk_picker()` predicate decides the widget; `_{e}_rules` keeps `("text", …)` byte-identical and FK-ness rides the separate `_{e}_fk` map. Shared helpers unchanged ⇒ no cross-app regression surface. |
| Blur-time `/validate` should check that the id exists. | `validate_<e>` (L1140–1151) takes **no session dependency** — adding one to reach the DB widens a hot, per-blur endpoint for a control whose values the server itself just produced. | **FR-7** narrows existence checking to submit (create/update, which already hold a session). Blur validation covers required-ness only; recorded as a resolved open question. |
| A required FK always has something to point at. | Nothing guarantees the target table is non-empty. A required FK with zero rows renders an **unfillable** form — strictly worse than today's text box, where a user could at least paste an id. | **FR-9** (new requirement, absent from v0.1) specifies the deterministic empty state: a disabled `— no <Target> yet —` option plus a link to `/ui/<target>/new`. |

**Resolved open questions:**
- **OQ-1 → Trigger on `@relation`, never on the name.** `DueInstance.sourceId` is the live
  counter-example; the schema already carries the authoritative answer.
- **OQ-2 → Options are route-supplied, not template-baked.** Enum parity is impossible; the four
  form-rendering call sites are the real surface area.
- **OQ-3 → No manifest in v1.** Schema plus the existing label heuristic fully determine the picker,
  so the drift dep-sets of `form.html` and `web.py` are unchanged.
- **OQ-4 → Existence validation at submit only.** Blur `/validate` stays session-free.
- **OQ-5 → Label override is deferred, not designed-out.** `display.yaml` `label_field` is the right
  eventual home; it costs `web.py` a new hash, so it waits for a second consumer to ask.
- **OQ-6 (raised and resolved at CRP R2) → A cleared picker performs a real clear.** The `— none —`
  option is a write, not just a widget: the shared write path drops empty values, so the clear is
  performed explicitly on update in FR-7's existing merge position. Naming the inability to clear as a
  limitation was the cheaper option and was rejected — the picker advertises the affordance.
- **OQ-7 (raised and resolved at CRP R2) → The picker keeps `required` and drops blur validation.**
  The required message is owned at two layers (native bubble, then the server backstop); the picker
  emits no `hx-post` to `/validate`, so both the attribute it keeps and the attributes it drops are
  decisions rather than inheritance from the text-input branch.

### 0.1 Lessons-Learned Hardening

> Consulted the ingested corpus and the pattern catalog with the routed decision-class keys
> (`#7 audience/presentation`, `#13 interactive-surface/rendering`), plus `det-req-kit/BACKEND_ROUTING.md`.
> Honest result: **thin.**

- **`contextcore lesson recall --project lessons-craft --task-type "interactive-surface/rendering"`**
  — ran; returned 6 hits, all at the flat 0.70 baseline and all off-domain (Supabase edge function,
  frontend test seam, Shopify migration). **No applicable lesson**; nothing applied, nothing recorded
  via `record-application`.
- **`python -m contextcore.learning.pattern_catalog recall "code × interactive-surface/rendering"
  "requirement × audience/presentation"`** — ran; returned `(none — browse fallback)`.
- **Markdown browse fallback (`PATTERN-CATALOG.md`)** — nearest-key entry is **PC-10 Deterministic
  Surface = Node Navigator** (`code × interactive-surface/rendering`). Only its "never a second loop"
  clause is in scope at this size, and it **was** applied: the picker rides the one existing
  select/validate path instead of introducing a parallel widget pipeline (FR-1, FR-7). The rest of
  PC-10 (node grammar, manifest recognizer, turn-loop) is **deliberately not** applied — imposing a
  navigator archetype on a single form control is the over-application this corpus warns about. Not
  cited via `pattern_catalog cite`, because reusing one clause of a K2 pattern is not the reuse the
  cite counter measures.
- **Backend re-check (`BACKEND_ROUTING.md`)** — re-ran the signal table after planning. FRs touch
  **entity / page / view** codegen only: no console script, no `--flag`, no store / migration /
  `app/db.py` seam (planning specifically *removed* the CLI-flag option, OQ-3). So
  `startd8-python-cascade` is **confirmed, not defaulted**, and no dual backend applies. The routing
  table's **security** row fired (untrusted input) → header `Trust boundary` plus two `security` risks
  and boundary-exercising Verifies on FR-7 / FR-8. Its **UX** row fired (audience) → header
  `Audience: end-user` plus user-observable Verifies on FR-4 / FR-9.

### 0.2 Design-Principle Hardening

> Checked the draft against `PRINCIPLE-INDEX.md` §2 filtered on the same keys. Five principles
> changed the draft; every change **removed** machinery rather than adding it.

- **[Genchi Genbutsu]** (`× fail-loud/validation-gate`, `× single-source/no-drift`) — forced the
  question "does the trigger bind to the authoritative artifact or to an inferred proxy?" The `*Id`
  suffix is a proxy; `@relation` is the artifact. Grounding whole-tree against the real household
  schema produced the `DueInstance.sourceId` counter-example → **FR-1** binds to `@relation` and its
  negative case is a Verify.
- **[Mottainai]** (`× idempotency/reuse`) — forced "is a later stage re-deriving what an earlier one
  already produced?" It was: v0.1 planned a second FK parser beside `_fk_map` and a second label
  policy beside `_default_label_field`. → **FR-2** makes one resolver the single source (with
  `_fk_map` re-expressed on it, not forked); **FR-4** reuses the existing label heuristic.
- **[Accidental-Complexity]** (META) — forced "is this adding a layer to compensate for something one
  general rule dissolves?" Two layers were removed before being built: the `pickers:` manifest (with
  its drift dep-set, CLI flag, and `FR-ED-16`-class skip-hook threading) and an `"fk"` branch inside
  the shared `_coerce` / `_field_error` helpers. → **FR-10** (schema-only, no new input) and the
  separate `_{e}_fk` map that leaves the shared helpers byte-identical.
- **[Context-Correctness-by-Construction]** (`× context-arrival/data-wiring`) — forced "can the
  required context silently arrive as `None`?" It can, and would have: options reaching `new_<e>` and
  `edit_<e>` but not the two error re-renders is precisely "slot exists, artifact never arrives", and
  it would only be visible *after* a validation failure. → **FR-3** names all four call sites,
  requires one helper, and makes the error path its Verify.
- **[Sotto]** (`× audience/presentation`, advisory) — the presence-gated, byte-identical-when-absent
  seam. → **FR-10** requires byte-identical output for a schema with no relation FK.

---

## Overview

Generated create/edit forms currently render foreign-key fields as raw text inputs, so an end user
must open a second tab, find the related record, and copy a CUID out of its URL to fill in
`assigneeId`. This adds a deterministic **relation picker**: any scalar field that a Prisma
`@relation(fields: […])` names as its FK renders as a populated `<select>` of the target entity's
rows, labelled by the target's existing zero-config label field, with server-side scoped validation
on submit. It is derived entirely from the schema the generator already parses — no new manifest, no
CLI flag, no autocomplete library, no per-app hand-written widget, `$0` LLM. Deliberately later:
typeahead, relation browsing, inline creation of the related record, and any `display.yaml`-driven
label override.

## Objectives

- O-1: A relation FK renders as a populated `<select>` on generated create and edit forms, with zero hand-written per-app widget code and `$0` LLM spend.
- O-2: No forged, stale, or cross-tenant FK id can be written through the HTMX surface, and no picker discloses a row the principal could not already read.
- O-3: Net new machinery is zero — no new manifest, no new CLI flag, no change to any owned kind's drift dep-set; an app with no relation FK regenerates byte-identically.
- O-4: Pilot P1-2 closes — a household user can complete a Chore create form without leaving the page to look up an id.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| security | A forged or stale FK id in the POST body is written unchecked; today it surfaces as an `IntegrityError` 500 or a dangling reference (pilot P0-3 / P0-4 class). | Scoped runtime existence check on create/update before commit; field-level error on miss (FR-7). | high |
| security | An unscoped options query puts another tenant's row labels and ids in the dropdown — a read-side leak on a surface that previously showed neither. | Options query and existence check reuse the same `owner_field` scoping as every other handler (FR-8); 404-not-403 posture preserved. | high |
| security | An **unscoped owning entity pointing at a scoped target** — a cell the uniformly-scoped pilot schema never exercises, so a household regen cannot catch it. Those routes resolve no principal today, so the options query is either unscoped (every tenant's labels and ids in the dropdown) or silently empty (an unfillable form with no signal). | Scoping resolves per entity on the **target**; a scoped target forces principal resolution on the rendering and accepting routes, and an unfiltered query against a scoped target is a generate-time failure rather than a silent fallback (FR-8). | high |
| security | A **stored** FK reference that is no longer in the option set — the target row is owned by another principal, was deleted, or the target is now empty — is silently dropped from the form. Optional: the form displays `— none —` over a value the column still holds (misreported state). Required: every subsequent save fails the required check, so another tenant deleting *their* row makes the owning tenant's row permanently un-editable — a denial-of-edit reachable across the tenant boundary. | The stored value always round-trips as a selected, non-selectable `— unavailable —` option carrying the stored id; scoping filters the *choices* without invalidating an existing reference (FR-6, FR-8, FR-9). | high |
| quality | Options supplied to some but not all four form-rendering routes, so the picker renders empty exactly on the validation-error re-render — the path users hit most. | One shared options helper, all four call sites named; the error path is the Verify (FR-3). | high |
| quality | FR-5's `— none —` advertises a clear the write path never performs: `_form_errors` drops empty values from `data` and `update_<e>` applies only `data`, so an optional picker submitted blank on **edit** leaves the previous FK in place and still returns 303 `?updated=1` — a success flash over a write that did not happen. Today's text input carries the identical latent defect, but the picker converts it into a promised affordance. | The clear is performed explicitly on update in the same merge position FR-7's existence check occupies — outside the shared `_form_errors` helper, which stays untouched (FR-7). | high |
| quality | A name-suffix trigger renders a picker for a polymorphic id with no target (`DueInstance.sourceId`). | Trigger on `@relation` only; the negative case is a named Verify (FR-1). | high |
| quality | A required FK whose target table is empty produces an unfillable form — worse than the text input it replaced. | Deterministic empty state: disabled option plus a link to create the target (FR-9). | medium |
| cost | An unbounded target ships every row as an `<option>` on every render — an uncapped query plus a sort per picker field, four render sites, twice per render for `Payment` — and typeahead/search are Non-goals, so v1 has no escape hatch. | Stated cardinality bound: above the generated threshold the field falls back to today's text input with its original hint, reusing the single degradation shape FR-3 already needs (FR-4). | medium |
| cost | A new manifest input would change `form.html`'s drift dep-set and require threading through five files plus the skip-hook (`FR-ED-16` class breakage). | Schema-only derivation; label override deferred to a Non-goal (FR-10). | medium |
| quality | Scope creep: "picker" drifts into typeahead, relation browsing, or inline creation of the related record. | Non-goals, enumerated with rationale. | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Relation-derived picker trigger.** A writable scalar field renders as a `<select>` if and only if some `@relation(fields: […])` on its model names it as an FK, so the `*Id` name suffix never triggers a picker. A picker field's structural hint is **replaced** (not deleted) with a control-appropriate instruction ("Choose the related record."), keyed on the relation-derived predicate rather than on the `*Id` suffix, so the field keeps its hint id and `aria-describedby` wiring and a non-relation `*Id` field keeps its existing copy-the-id hint. More precisely, the predicate the replacement keys on is the field **actually rendering as a select**, so a picker field that degrades to a text input (an absent `options` key per FR-3, or an over-threshold target per FR-4) keeps its original copy-the-id hint rather than instructing the user to choose from a dropdown that is not there. Touches: Chore, Medication, Payment, DueInstance, <entity>/form.html. Verify: given the household schema, `Chore.assigneeId` and `Medication.memberId` render `<select name="assigneeId">` and `<select name="memberId">`, while `DueInstance.sourceId` — a documented polymorphic reference with no `@relation` — still renders `<input type="text">`; the Chore form carries no "copy from its detail page URL" string, its `assigneeId` select still carries `aria-describedby="hint-assigneeId"` with the replacement text, and `DueInstance.sourceId`'s hint is unchanged. Serves: O-1
- **FR-2 — One shared FK-target resolver.** A single helper maps each FK scalar to its `(target_model, ref_column)` from `@relation`, and `sqlmodel_renderer._fk_map` is re-expressed on top of it rather than kept as a second parser. The resolver's domain is the whole relation grammar, not the picker's subset: it is **composite-complete** — one entry per zipped `(field, reference)` pair, matching what `_fk_map` emits today — because the picker's exclusion of composite and list relations (a Non-goal) belongs to the widget predicate, and a composite-skipping resolver would silently drop `foreign_key=` from generated `tables.py`. Touches: Chore, Member, <entity>/form.html, app/web.py. Verify: given the household schema, the resolver returns `assigneeId → ("Member","id")`, and the existing `sqlmodel-tables` output is byte-identical before and after the re-expression (`--check` clean, no regenerated diff); given a composite `@relation`, the resolver returns one entry per zipped pair, every one of those columns still carries `foreign_key=` in the regenerated `tables.py`, and none of them renders as a select. Serves: O-3
- **FR-3 — Options reach every form render.** One generated per-entity options helper supplies value/label pairs for each picker field and is called by all four routes that render `form.html`: `new_<e>`, the `create_<e>` validation-error re-render, `edit_<e>`, and the `update_<e>` validation-error re-render. The four-site count is an **invariant, not an enumeration**: a generated `web.py` contains exactly four `form.html` responses per entity, every one of them passing the options key, and FK existence errors (FR-7) merge into the existing errors mapping rather than adding a fifth or sixth render site. The picker set the helper covers is the **same** `_writable_fields(schema, entity, human_only)` set the form inputs and `_{e}_rules` already use, so an owned FK column gets no options query. The **consumer** side of the contract is specified too, not just the producer: `options` spans two separately-owned, separately-hashed drift kinds (`htmx-form` owns `form.html`, `fastapi-web` / `fastapi-web-forms` own `web.py`) that skip and hand-edit independently, so a consumer repo can legitimately hold the two halves at different versions. The template therefore guards `options` exactly as it already guards `prefill` and `errors`, and an **absent** key degrades rather than raising: the field renders the pre-picker text input with its original hint (FR-1). A key that is *present but carries no rows* for a field is a different case — that is FR-9's empty-target state, not a degradation. Touches: app/web.py, <entity>/form.html. Verify: given a POST to `/ui/chore` that fails validation on a different field, the returned form's `assigneeId` select still lists every eligible Member rather than being empty, and re-selects the submitted value; the generated `web.py` has exactly four `form.html` responses per entity, all passing options; and rendering `form.html` with a context that omits `options` entirely (the shape a stale template or a stale `web.py` produces) yields a text input for `assigneeId` rather than raising, while `edit_<e>`'s narrowest three-key context still renders the picker. Serves: O-1
- **FR-4 — Zero-config option labels.** Each option's value is the target's referenced column and its label is the target's existing zero-config label field (`name` / `title` / `label` / `headline`), falling back to the raw id when the target has none. Options are **deterministically ordered** by the label field ascending, ties broken by the referenced column, with label-less rows sorted last — so the dropdown does not reorder between environments and FR-3's and FR-9's assertions are stable. The ordering is **dialect-independent**: it is applied over the fetched `(value, label)` pairs rather than expressed as a SQL `ORDER BY`, because "label-less last" is `NULLS LAST` semantics and SQLite — the pilot's and the fixtures' engine — sorts `NULL` *first* on a plain ascending order, which would make this Verify pass or fail by backend. Targets are additionally assumed to be **small enumerable sets**: the options query is bounded by a single generated threshold, and a target exceeding it renders as today's text input with its original hint (FR-1) rather than as a select — the same degradation shape FR-3's absent-`options` case uses, so the bound costs no manifest, no flag, and no new hash. Touches: Member, <entity>/form.html. Verify: given a Member named "Sam", the Chore form's `assigneeId` option reads `Sam` with `value="<Sam's id>"`; given a target with no label-heuristic column, the option text is the id and the form still submits; given three target rows seeded out of alphabetical order the rendered `<option>` sequence is label-ascending with the label-less row last **under SQLite** (the `NULLS LAST` case, distinct from a target with no label column at all, which orders by the referenced column alone); given a target holding one row more than the threshold the field renders `<input type="text">` with its original copy-the-id hint and no options query result is shipped; and given a Member named `<script>alert(1)</script>` the option text is HTML-escaped in the rendered form. Serves: O-1
- **FR-5 — Optionality-correct leading option.** An **optional** FK gets a leading submittable blank `— none —` option; a **required** FK gets a leading **non-submittable placeholder** (`<option value="" disabled selected>— select a <Target> —</option>`), never a pre-selected real row — so an untouched required picker submits empty and fails the existing required check rather than silently writing whichever row the DB returned first. The required picker **keeps** the `required` attribute the enum select already emits, which makes the required message a **two-layer** guarantee with an explicitly named owner per layer: the browser's native constraint validation refuses the submit first (the disabled `value=""` placeholder cannot satisfy it), and the server-side required check is the defense-in-depth backstop for every non-browser client. FR-FH-11's `#err-<name>` slot is therefore *not* the surface for the untouched-required case in a browser — the native bubble is — and the Verify below is a server-layer assertion, stated as such rather than read as a user-visible browser outcome. The blank `— none —` submitting "as unset" is a create-path statement; what an empty submission does on **update** is specified in FR-7. Touches: Chore, Medication, <entity>/form.html. Verify: given the household schema, `Chore.assigneeId` (`String?`) offers a blank option that submits as unset while `Medication.memberId` (required) offers a first option with `value=""` and `disabled`; submitting the Chore form with the blank chosen stores a null `assigneeId` and returns 303; submitting the Medication form with the required picker untouched returns a 200 form with a field-level **required** error and no row written (a TestClient assertion exercising the server backstop, not the browser path); and the rendered required select carries `required` as a deliberate emission rather than an inherited one. Serves: O-1
- **FR-6 — Existing prefill precedence honored.** The picker's selected option follows the same precedence the enum select already uses: submitted or prefilled value, else the current record's value, else the leading option from FR-5 (the blank `— none —` when optional, the disabled placeholder when required) — never a real row chosen by position. One cell is specified explicitly rather than left to the fall-through: when the current record's stored value is **not in the option set** — the target row belongs to another principal, was deleted, or the target has no eligible rows at all (FR-9) — the precedence does **not** drop to the leading option. The stored value round-trips as an additional **selected, non-selectable `— unavailable —` option carrying the stored id**, ordered last, so a save that edits other fields preserves the reference and a required picker in that state cannot lock the row out of editing. That option carries the opaque id only — never a label read from a row the principal cannot see — so round-tripping the reference discloses nothing the principal did not already hold. Touches: app/web.py, <entity>/form.html. Verify: given `GET /ui/chore/new?assigneeId=<member-id>` that Member's option carries `selected`, given `GET /ui/chore/<id>/edit` on an already-assigned Chore the assigned Member's option carries `selected`, given `GET /ui/medication/new` the `selected` attribute sits on the disabled placeholder rather than on any Member option, and given a Chore owned by principal A whose `assigneeId` points at principal B's Member the edit form carries a selected `— unavailable —` option holding that id with no label from B's row, a `POST` changing only the title returns 303 with `assigneeId` unchanged, and the same fixture with a **required** FK saves rather than returning a required error. Serves: O-1
- **FR-7 — Server-side FK existence validation on submit.** Create and update validate every writable picker field (the FR-3 set) against the target's rows before commit via a separate generated FK map, merging any miss into the same errors mapping the existing error branch consumes so no new render site appears, while the shared `_coerce` / `_field_error` helpers and the `_{e}_rules` kinds stay unchanged and blur `/validate` remains session-free — the picker does not participate in blur validation at all, as stated below. An empty submitted value is never existence-checked, and the two submit paths **differ**: on create an optional FK submitted empty stores null, while on update the shared write path would not clear it at all — `_form_errors` omits empty values from the applied `data` mapping, so a `— none —` selection would leave the previous FK in place and still return 303 `?updated=1`. The clear is therefore performed **explicitly on update**, in the same merge position this FR's existence check already occupies (outside `_form_errors`, which stays byte-identical for every generated app), so the affordance FR-5 advertises is the write the route performs. A required FK submitted empty produces the required error, not "not a valid choice", on both paths. The picker also does **not** carry the blur `hx-post="/ui/<e>/validate"` triple the text inputs carry — a select's value is chosen rather than typed, and firing "This field is required." at an untouched required picker on tab-past is noise rather than validation — so `validate_<e>` staying session-free (OQ-4) is a deliberate exclusion of the picker, not an inherited accident. Touches: app/web.py, Chore, Medication. Verify: given `POST /ui/chore` with `assigneeId=not-a-real-id` the response is a 200 form carrying a field-level error on `assigneeId` with no row written — not a 500 — and given a valid id the response is a 303 as today; given `POST /ui/chore/<id>` with `assigneeId=not-a-real-id` the response is a 200 form with the field-level error and the row unchanged; given `assigneeId=""` on the optional FK at **create** the response is a 303 with null stored; given `assigneeId=""` at **update** on a Chore that currently has an assignee the response is a 303 **and the stored column is `None` afterward, not the prior id**; given `memberId=""` on the required FK the response is a 200 with the required error; a coercion error and an FK-miss error return through the same branch, both with populated options; and the rendered picker carries none of the three blur `hx-*` attributes. Serves: O-2
- **FR-8 — Tenant-scoped options and validation.** Scoping is resolved **per entity**, not per app: the target's predicate is the target's own owner field when the target is a scoped entity and none when it is not, independently of whether the owning entity is scoped. All four cells of (owner scoped/unscoped × target scoped/unscoped) are specified, and a **scoped target forces principal resolution on every route that renders or accepts that picker even when the owning entity is unscoped** — an unfiltered query against a scoped target is never emitted, and a non-owned id is reported as an invalid choice rather than as a distinguishable "exists but forbidden". Scoping governs the **choices**, not the validity of a reference already stored: an id filtered out of the options is still preserved on the owning row. On update, a submitted value byte-identical to the row's currently stored value is an *unchanged reference*, not a new write, and is therefore not existence-checked — that is precisely FR-6's `— unavailable —` round-trip. A submitted value that **differs** from the stored one is always checked against the scoped target, so the carve-out cannot be used to write a non-owned id. Touches: app/web.py, Member. Verify: given two principals each owning one Member, principal A's Chore form lists only A's Member, and a `POST /ui/chore` from A carrying B's member id returns a 200 form with a field-level error identical to the nonexistent-id case and writes nothing; given an **unscoped** Chore pointing at a **scoped** Member, principal A's `/ui/chore/new` lists only A's Members, an anonymous request is refused rather than served unscoped, and A posting B's member id returns that same field error; and given A's Chore already storing B's member id, A re-submitting that same id unchanged saves without an error while A submitting any *other* non-owned id returns the field error. Serves: O-2
- **FR-9 — Empty-target empty state.** When a picker's target has no eligible rows the select renders a single disabled `— no <Target> yet —` option plus a link to that target's create page, and a required picker in that state cannot be satisfied by a forged id. On an **edit** form the empty state never discards a stored reference: the zero-row select still renders FR-6's selected `— unavailable —` option carrying the stored id beside the `— no <Target> yet —` option and the create link, so saving an otherwise-unchanged row preserves the FK instead of silently clearing it. The empty target is the zero-row end of the cardinality range; the over-threshold end is FR-4's text-input fallback, not a second empty state. Touches: <entity>/form.html, app/web.py, Member. Verify: given zero Members, the Chore create form shows a disabled `— no Member yet —` option and a working link to `/ui/member/new`, and posting a fabricated `assigneeId` in that state returns the form with a field-level error; and given zero *eligible* Members but a Chore already storing a member id, the edit form carries both the `— unavailable —` stored-value option and the create link, and a POST changing only the title preserves the stored `assigneeId`. Serves: O-4
- **FR-10 — Presence-gated and dep-set-preserving.** The picker derives from the Prisma schema alone: no new manifest, no new CLI flag, and no change to the drift dep-set or header hash count of `htmx-form`, `fastapi-web`, or `fastapi-web-forms`; a schema with no relation FK regenerates byte-identically, and within a picker-bearing schema an entity with no picker field regenerates byte-identically too — the route-signature changes the picker needs are gated per entity, not applied app-wide. FR-4's cardinality threshold is a generated constant, not a manifest key or a flag. Touches: <entity>/form.html, app/web.py, DueInstance. Verify: given a schema with no `@relation`, `startd8 generate backend` output is byte-identical to the pre-change output; given a schema mixing one picker-bearing and one picker-free entity, the picker-free entity's generated route block is byte-identical to its pre-change rendering; given the household schema, `startd8 generate backend --check` is clean immediately after a regenerate and no `--picker` flag exists. Serves: O-3

## Non-goals

- No autocomplete or typeahead vendor library — no Select2 / Choices.js / Tom Select / combobox dependency, and no client-side search over options. A plain `<select>` only.
- No relation or graph browser — no popup to explore the target entity, and no nested related-record navigation from the form.
- No confirm-walk — the picker introduces no multi-step confirm sequence; the existing PRG + `?created=` contract (`FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md`) is unchanged.
- Not the onboarding archetype — this is the item the onboarding REQ's non-goals deferred, not an extension of `onboarding:`; no `/welcome`, tips, or checklist surface is touched.
- Not the `editors:` bulk surface — no bulk child-field editing and no picker inside `editor-form` templates in v1; `EDITORS_ARCHETYPE_REQUIREMENTS.md` is cited as promotion-door precedent only.
- Not the import path — `import_codegen` / `import_surface` FK resolution is untouched (`GENERATED_IMPORT_PATH_REQUIREMENTS.md` owns it).
- No inline creation of the related record — no "add new Member" modal from the Chore form; the empty state links to the existing create page instead (FR-9).
- No `display.yaml` `label_field` override for option labels — deferred, not designed-out. `web.py` has no `display.yaml` dependency today; honoring the override there would add a hash to `fastapi-web` / `fastapi-web-forms` and require threading `display_text` through `owned_file_in_sync` / `check_drift` / `assembler` / the skip-hook. It waits for a second consumer.
- No FK label denormalization on list or detail — `list.html` / `detail.html` keep showing the raw id; making them read the target's label is a separate change with its own query cost.
- No composite multi-column FK pickers and no list or many-to-many relations — a composite `@relation` and a `Member[]`-style relation both fall back to today's rendering. The exclusion lives in the **picker predicate**, never in the shared resolver, which stays composite-complete so the generated `foreign_key=` constraints survive (FR-2).
- No blur-time existence validation, and no blur-time picker validation at all — the picker emits none of the text inputs' `hx-post` / `hx-trigger="blur changed"` / `hx-target` attributes, and `validate_<e>` stays session-free (OQ-4, FR-7).
- No large-target affordance in v1 — above FR-4's cardinality threshold the field falls back to today's text input rather than gaining search, paging, or a modal browser. The fallback is the bound; a better large-target control waits for a consumer that has one.

## Owned fields

Only humans enter: none

No new owned field is introduced. The picker changes *how* an existing FK column is entered, not who
may write it; the `human_inputs.yaml` owned-field policy is unchanged and continues to drop owned
columns from every write surface before a picker is ever considered.

This claim holds only because **all three consumers share one filtered set**: the picker set, the
generated options helper, and the generated `_{e}_fk` map are all derived from the same
`_writable_fields(schema, entity, human_only)` set that already filters the form inputs and
`_{e}_rules` — never from the raw relation-target map. An FK column owned by `human_inputs.yaml`
therefore gets no widget, no options query, and no existence-check entry.

## Contract projection

- **Backend:** startd8-python-cascade
- **Vocabulary home (cite):** `det-req-kit/SCHEMA.md` §8 (cascade vocabulary: `entity` · `page` ·
  `view` · `completeness` · `ai-assist`) → `KICKOFF_AUTHORING_CONTRACT.md` §2.x. Generator seam (cite,
  do not restate): `src/startd8/backend_codegen/htmx_generator.py`,
  `src/startd8/backend_codegen/sqlmodel_renderer.py`.

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| Chore | entity | structure | Optional FK `assigneeId String?` → Member; the pilot P1-2 surface |
| Medication | entity | structure | Required FK `memberId` → Member; the disabled-placeholder (no pre-selected row) case |
| Payment | entity | structure | Two FKs on one form (`billId` required, `memberId?` optional) |
| Member | entity | structure | Picker target; label from the existing `name` heuristic |
| DueInstance | entity | structure | Negative case: `sourceId` is polymorphic with no `@relation`, so it stays a text input |
| <entity>/form.html | view | structure | Owned kind `htmx-form`; select widget, leading option (blank or disabled placeholder), ordered options, `— unavailable —` stored-value round-trip, replaced hint, empty state, guarded-`options` degradation |
| app/web.py | view | structure | Kinds `fastapi-web` / `fastapi-web-forms`; options helper (bounded, Python-ordered), four call sites, FK existence check, update-path clear, tenant scoping, per-entity route gating |
| <entity>/list.html | view | structure | Unchanged — FK label denormalization is a Non-goal |

---

*v0.2 — Post-planning self-reflective update. 10 assumptions corrected: 3 requirements narrowed
(FR-2, FR-4, FR-6 — existing machinery already met them), 1 added (FR-9, the empty-target state),
2 deferred to Non-goals (`display.yaml` label override, blur-time existence validation), 1 reframed
at the correct layer (options are route-supplied, not template-baked — FR-3), and 2 mechanisms
deleted before they were built (the `pickers:` manifest, an `"fk"` branch in the shared coercion
helpers). 5 open questions resolved. Lessons recall and pattern recall were run and recorded as thin
in §0.1; 5 design principles applied in §0.2. Ready for CRP-lite (S-size: one Appendix-C round plus
A/B triage, per `BACKEND_ROUTING.md`).*

*v0.4 (post-CRP R1) — CRP Round R1 (Composer) triaged: **12 suggestions accepted, 0 rejected**
(requirements-side R1-F1…F6 merged here; plan-side R1-S1…S6 merged into `FK_PICKER_PLAN.md`, with
R1-S1's hint change given an FR home in FR-1), plus R1's cap-bounded label-escaping observation folded
into the FR-4 Verify. No new FR was added and no deleted mechanism was re-imported: the `pickers:`
manifest, the `--picker*` flag, and the `"fk"` coercion kind all stay deleted, and no suggestion
touched `_coerce` / `_field_error` / `_{e}_rules`. Body edits: FR-5/FR-6 closed a silent required-picker
default (a non-submittable placeholder replaces browser-preselected option 0); FR-3/FR-7 turned the
"four render sites" count into an invariant with FK errors merging into the existing errors mapping;
FR-8 replaced app-level tenancy with the per-entity 2×2 and made a scoped target force principal
resolution (new high-severity Risks row). Dispositions in Appendix A; Appendix C round retained intact.*

*v0.5 (post-CRP R2) — CRP Round R2 (Composer) triaged: **5 of 5 requirements-side suggestions accepted,
0 rejected** (R2-F1…F5 merged here; plan-side R2-S1…S5 merged into `FK_PICKER_PLAN.md`). Version bumped
to 0.5 rather than 0.4.1 because the body changes are material: R2 closed three **write-path** gaps that
R1's structural pass could not see. No new FR was added and no deleted mechanism was re-imported — the
`pickers:` manifest, the `--picker*` flag, and the `"fk"` coercion kind all stay deleted, and no
suggestion touched `_coerce` / `_field_error` / `_form_errors` / `_{e}_rules`. Body edits: **FR-7** now
distinguishes create from update for an empty submission and performs the clear explicitly, so FR-5's
`— none —` is a write and not just a widget (new high `quality` Risks row); **FR-6 / FR-8 / FR-9** specify
the stored-value-not-in-option-set cell with a selected `— unavailable —` round-trip plus an
unchanged-reference carve-out that cannot be used to write a non-owned id (new high `security` Risks row);
**FR-5** names the layer that owns the required message and **FR-7** excludes the picker from blur
validation deliberately; **FR-4** makes the ordering dialect-independent and bounds target cardinality,
with the over-threshold field falling back to a text input; **FR-3** specifies the consumer half of the
`options` contract, reusing that same one degradation shape; **FR-1 / FR-10** follow through (the hint
replacement keys on actually rendering a select; the route-signature change is gated per entity, so a
picker-free entity stays byte-identical). One plan-side item also landed here because it is a
requirements-level contract: **FR-2** now states the resolver is composite-complete, since the widget's
composite exclusion belonging to the resolver would have dropped `foreign_key=` from generated
`tables.py` under a step whose premise is "no output change" (R2-S1). Dispositions in Appendix A; both
Appendix C rounds retained intact.*

## Appendix A — Accepted (with where merged)

CRP R1: 12 of 12 suggestions accepted, 0 rejected. CRP R2: 5 of 5 requirements-side suggestions
accepted, 0 rejected. Per-ID dispositions and merge locations for this
document's suggestions are recorded in the **Appendix A: Applied Suggestions** table of the Iterative
Review Log below (the designated home per the reviewer instructions); plan-side dispositions live in
`FK_PICKER_PLAN.md`'s Appendix A.

## Appendix B — Rejected (with rationale)

Nothing rejected in R1 or R2. See the **Appendix B: Rejected Suggestions** table below.

## Appendix C — Incoming review rounds

Rounds R1 and R2 (Composer, 2026-08-14) are retained in full in the **Appendix C: Incoming Suggestions**
section of the Iterative Review Log below. Rounds are never stripped after triage.

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
| R1-F1 | Required picker must not silently pre-select option 0: optional FK gets a submittable blank `— none —`, required FK gets a non-submittable disabled placeholder; drop FR-6's "first option (required)" clause. | R1 / Composer | **Merged:** FR-5 retitled and restated ("Optionality-correct **leading** option") with the `<option value="" disabled selected>— select a <Target> —</option>` form; FR-6's required-branch clause replaced with "the leading option from FR-5 … never a real row chosen by position". Verifies added: required picker untouched → 200 + required error, no row written, first option `value=""` + `disabled` (FR-5); `selected` sits on the placeholder, not on a Member option (FR-6). | 2026-08-14 |
| R1-F2 | FR-4 fixes option value and label but not **order**; order deterministically by label ascending, ties by referenced column, label-less rows last. | R1 / Composer | **Merged:** ordering sentence added to FR-4 after the label-fallback sentence, with the cross-FR rationale (stops environment-dependent reordering; makes FR-3/FR-9 assertions stable). FR-4 Verify extended: three rows seeded out of alphabetical order render label-ascending with the label-less row last. | 2026-08-14 |
| R1-F3 | FR-7's prose covers create **and** update but its Verify covers only create; add the update path plus the two blank-value cases (optional empty → skip check; required empty → required error). | R1 / Composer | **Merged:** FR-7 gained an explicit "an empty submitted value is never existence-checked" sentence, and its Verify now names five cases: create miss → 200 + error; create valid → 303; **update** miss → 200 + error, row unchanged; optional `""` → 303 with null stored; required `""` → 200 + required error. | 2026-08-14 |
| R1-F4 | FR-8 is written app-level but scoping is per-entity; specify the (owner scoped/unscoped × target scoped/unscoped) 2×2 and require a scoped target to force principal resolution even when the owning entity is unscoped. Add a Risks row. | R1 / Composer | **Merged:** FR-8's "In a tenant-scoped app" opening replaced with the per-entity resolution rule + all four cells + the scoped-target-forces-principal requirement + "an unfiltered query against a scoped target is never emitted". FR-8 Verify extended with the unscoped-Chore × scoped-Member fixture (anonymous request refused, not served unscoped). New **high** `security` Risks row filed for the unscoped-owner × scoped-target cell, naming that the uniformly-scoped pilot cannot catch it. Plan-side twin: R1-S5. | 2026-08-14 |
| R1-F5 | FR-3's "four render sites" is falsified by FR-7 unless FK errors merge into the existing `errors` mapping; make the count an invariant and give FR-7 a no-new-render-site Verify. | R1 / Composer | **Merged:** FR-3 gained the "invariant, not an enumeration" sentence (exactly four `form.html` responses per entity, all passing options; FK errors merge rather than adding a fifth/sixth site) plus a generator-level Verify. FR-7 restated to merge misses "into the same errors mapping the existing error branch consumes so no new render site appears", with the same-branch Verify (coercion error and FK-miss both return with populated options). Plan-side twin: R1-S3, structural guard R1-S6. | 2026-08-14 |
| R1-F6 | Only FR-1 carries "writable"; state that the picker set, options helper, and `_{e}_fk` map all derive from the same `_writable_fields(schema, entity, human_only)` set. | R1 / Composer | **Merged:** "Owned fields" section gained the one-set paragraph (all three consumers share the filtered set; an owned FK column gets no widget, no options query, no existence-check entry). FR-3 wording now names the shared `_writable_fields(…)` set; FR-7 now reads "every writable picker field (the FR-3 set)". | 2026-08-14 |
| R1-Obs | Cap-bounded R1 observation (no ID assigned by the reviewer): option labels are row content rendered at request time rather than `html.escape`d at generate time like the enum branch; a one-line Verify would close it cheaply on FR-4. | R1 / Composer | **Merged** as a Verify only — no FR added, no mechanism introduced: FR-4's Verify now asserts a Member named `<script>alert(1)</script>` renders HTML-escaped. Accepted because it is a one-line assertion on an existing guard (Jinja autoescape), not new machinery. | 2026-08-14 |
| R2-F1 | FR-5's blank `— none —` and FR-7's "optional empty stores null" hold on create only: `_form_errors` drops empty values from `data` (L992) and `update_<e>` applies only `data` (L1212–1213), so a cleared picker on edit is a no-op that still returns 303. Either perform the clear (outside `_form_errors`) or name the limitation; add a Risks row. | R2 / Composer | **Merged, taking the perform-the-clear branch** — naming it as a limitation would leave a promised affordance silently failing. FR-7 now distinguishes create from update for the empty case and performs the clear in the **same merge position the existence check already occupies**, so no new machinery and no touch to `_form_errors`; FR-5 marks "submits as unset" as a create-path statement and defers the update path to FR-7. New **high** `quality` Risks row filed for the class (promised-affordance-over-a-no-op-write). FR-7 Verify gained the update-clear case (stored column is `None` afterward, response still 303) beside the existing create case as a negative control. Not a re-proposal of R1-F3: this falsifies one of R1-F3's two paths. | 2026-08-14 |
| R2-F2 | FR-6 × FR-8 leave the **stored value not in the option set** unspecified (target row owned by another principal, deleted, or empty target on an edit form): required ⇒ the row becomes permanently un-editable, optional ⇒ the form misreports stored state. Round-trip the stored value; scoping must filter choices without invalidating an existing reference. | R2 / Composer | **Merged:** FR-6 gained the explicit not-in-option-set branch — the stored value round-trips as a **selected, non-selectable `— unavailable —` option carrying the id only** (never a label from an unreadable row), ordered last, so a save preserves the reference and a required picker cannot lock the row. FR-8 now states that scoping governs the *choices*, not the validity of a stored reference, with the minimum carve-out that closes the obvious hole: on update an **unchanged** submitted value is not existence-checked, while any value **differing** from the stored one is always checked against the scoped target — so the round-trip cannot be used to write a non-owned id. FR-9 extends the empty state to edit forms carrying a stored value. New **high** `security` Risks row naming the cross-tenant denial-of-edit. Distinct from R1-F4's row-visibility matrix. | 2026-08-14 |
| R2-F3 | Name the layer that surfaces a required-picker error (native `required` blocks the disabled-placeholder submit client-side, so FR-5's Verify is green at the API layer only) and state whether the picker participates in blur validation. | R2 / Composer | **Merged as two explicit decisions rather than inheritance.** FR-5: `required` is **kept**, and the required message is stated as a two-layer guarantee with a named owner per layer — native bubble first, server check as the defense-in-depth backstop for non-browser clients — with the Verify relabelled as a server-layer assertion and FR-FH-11's `#err-<name>` slot explicitly *not* the browser surface for the untouched-required case. FR-7: the picker **does not** emit the blur `hx-post` / `hx-trigger` / `hx-target` triple (a select's value is chosen, not typed; firing "required" on tab-past is noise), making OQ-4's session-free `validate_<e>` a deliberate exclusion; mirrored into the Non-goals and asserted in FR-7's Verify. | 2026-08-14 |
| R2-F4 | FR-9 specifies the zero-row target and nothing bounds a large one: an uncapped `select(Target)` plus a sort over an unindexed label column, per picker field on all four renders, with typeahead a Non-goal. Either bound it or accept it in Risks. | R2 / Composer | **Merged, taking the bound** — and paid for with **no new machinery** by reusing FR-3's degradation shape: FR-4 now states the small-enumerable-set assumption, bounds the options query by a single generated threshold constant (not a manifest key or flag, asserted in FR-10), and sends an over-threshold target to today's text input with its original hint. FR-1's hint replacement was re-keyed on *actually rendering a select* so the fallback keeps the correct copy-the-id hint; FR-9 names the two ends of one cardinality range rather than two empty states; a Non-goal records that a better large-target control waits for a consumer. New **medium** `cost` Risks row. | 2026-08-14 |
| R2-F5 | FR-3 specifies the `options` **producer** but not the **consumer**: the four sites pass three different context shapes, every existing template variable is defensively guarded, and `htmx-form` / `fastapi-web*` are separately-owned skippable drift kinds that can sit at different versions. State the guard and the degradation. | R2 / Composer | **Merged:** FR-3 gained the consumer clause — the template guards `options` exactly as it guards `prefill` / `errors`, an **absent** key degrades to the pre-picker text input rather than raising, and a key **present but carrying no rows** is FR-9's empty state instead (the two cases were conflatable and are now distinguished). Degradation deliberately reuses R2-F4's single fallback shape, so the pair carries one degradation, not two. Verify added: rendering `form.html` with `options` omitted yields a text input rather than an exception, and `edit_<e>`'s narrowest context still renders the picker. Plan-side twin: R2-S5 (the version-skew assertion). | 2026-08-14 |

Two body edits here were requested by plan-side suggestions, whose disposition rows live in
`FK_PICKER_PLAN.md`'s Appendix A, so no S-prefix disposition is recorded here (protocol invariant:
F-IDs only in this document's appendix): the `_structural_hint` replacement sentence in **FR-1**
(R1-S1) and **FR-2**'s composite-completeness clause plus its composite Verify (R2-S1 — the resolver's
domain is a requirements-level contract because it is what keeps FR-2's byte-identity claim true).

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — R1 triaged 12/12 accepted, 0 rejected; R2 triaged 5/5 requirements-side accepted, 0 rejected) |  |  |  |  |

### Areas Substantially Addressed

(No area has reached the threshold of 3 accepted suggestions yet. Counts below are this document's own
Appendix A F-ID counts after R2; the R1 label-escaping observation is merged but carries no reviewer
area and is excluded from the counts.)

### Areas Needing Further Review

- **Architecture**: 1/3 suggestions accepted (need 2 more) — R1-F5
- **Interfaces**: 2/3 suggestions accepted (need 1 more) — R2-F3, R2-F5
- **Data**: 2/3 suggestions accepted (need 1 more) — R1-F2, R1-F6
- **Risks**: 2/3 suggestions accepted (need 1 more) — R2-F1, R2-F4
- **Validation**: 2/3 suggestions accepted (need 1 more) — R1-F1, R1-F3
- **Ops**: 0/3 suggestions accepted (need 3 more)
- **Security**: 2/3 suggestions accepted (need 1 more) — R1-F4, R2-F2

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — Composer — 2026-08-14

- **Reviewer:** Composer
- **Date:** 2026-08-14 (UTC)
- **Scope:** Requirements-side (F-prefix) review of `FK_PICKER_REQUIREMENTS.md` v0.2, weighted by
  `_crp/FOCUS_FK_PICKER.md`. Grounded against the cited generator seams:
  `sqlmodel_renderer._fk_map` (L144–171), `htmx_generator._structural_hint` (L597–620),
  `_form_input_html` (L639–774), `render_form_template` (L797/817), `_entity_routes` (L1075–1224),
  `render_web`'s `scoped` set (L1322–1324). Onboarding archetype grammar and FR-FH-11 layout not
  re-litigated, per focus file.

**Executive summary**

- The §0 reflection is unusually strong: the four corrections that *removed* machinery (no `pickers:`
  manifest, no `"fk"` kind, separate `_{e}_fk` map, reuse of `_default_label_field`) all hold against
  the real code. No suggestion below re-opens them.
- Highest-value gap is **FR-5 × FR-6 interaction**: a required `<select>` with no blank option is
  pre-selected at index 0 by every browser, so an untouched required picker silently writes the first
  option. That is a new silent-default on the exact path FR-7 exists to harden (R1-F1).
- Second: **FR-3's "four render sites" is falsified by FR-7 as written** — an FK-miss re-render is a
  fifth and sixth `form.html` response unless the FK error merges into the existing `errors` mapping
  before the single error branch (R1-F5). This is the focus file's weight #2, one level deeper.
- Third: **FR-8 is written app-level ("In a tenant-scoped app") but scoping is per-entity.** The
  unstated cell — unscoped owner entity pointing at a scoped target — is a live read-side leak,
  because those routes resolve no principal at all today (R1-F4). Focus weight #3.
- FR-4 specifies option *content* but not option *order*; with no `ORDER BY`, dropdown order is
  whatever the DB returns, which also makes FR-6's "first option (required)" and FR-9's assertions
  order-dependent (R1-F2).
- FR-7's prose covers create **and** update; its Verify covers only create, and the blank/optional
  submission cases are unspecified (R1-F3).
- The owned-field policy is asserted unchanged, but only FR-1 carries the "writable" qualifier; FR-3
  and FR-7 are written over "each picker field" (R1-F6).
- **Observation (no ID, cap-bounded):** option labels are row content rendered at request time rather
  than `html.escape`d at generate time like the enum branch (L736). Jinja autoescape is the only
  guard; a one-line Verify (a target row named `<script>alert(1)</script>` renders escaped) would
  close it cheaply on FR-4.
- Non-goals are grounded and each carries a cost reason; nothing below asks to re-import a deleted
  mechanism. FR-10's "no new manifest / no new dep-set" claim survives review.

**Suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | FR-5's "a required FK gets none" combined with FR-6's "else the blank option (optional) or **first option (required)**" specifies a silent default. Restate FR-5 as: an **optional** FK gets a submittable blank `— none —`; a **required** FK gets a **non-submittable placeholder** (`<option value="" disabled selected>— select a <Target> —</option>`), and delete FR-6's "first option (required)" clause. | A required `<select>` whose first `<option>` carries a value is pre-selected by the browser, so a user who never opens the dropdown writes whichever row the DB returned first. That is the silent-arrival failure §0.2 cites Context-Correctness-by-Construction against, on the same submit path FR-7 hardens — and it makes the written value depend on option order (see R1-F2). Today's text input at least produced an empty required error. | FR-5 (restate), FR-6 (drop the required-branch clause), and the FR-6 Verify | Runtime: submit the Chore create form with `memberId`-style required picker untouched → 200 form with a field-level **required** error and no row written; assert the rendered required select's first option has `value=""` and `disabled`. |
| R1-F2 | Data | high | FR-4 fixes option value and label but not **order**. Add: options are ordered deterministically by the label field ascending (ties broken by the referenced column), with label-less rows last. | With no ordering clause the generated query is `select(Target)` and row order is engine/insert-order dependent, so (a) the dropdown reorders between environments, (b) FR-6's "first option" resolves nondeterministically, and (c) FR-9's and FR-3's assertions become order-flaky the moment the fixture has two rows. Ordering is free (one `.order_by`) and makes three other FRs testable. | FR-4, after the label-fallback sentence; mirror into the FR-4 Verify | Unit/runtime: seed three target rows out of alphabetical order and assert the rendered `<option>` sequence is label-ascending; assert a label-less row sorts last. |
| R1-F3 | Validation | medium | FR-7's prose says "**Create and update** validate every picker field", but its Verify exercises only `POST /ui/chore`. Extend the Verify to the update route and add the two blank-value cases: an **optional** picker submitted empty must skip the existence check entirely, and a **required** picker submitted empty must produce the required error, not "not a valid choice". | An unverified half of a security guard is the half that gets omitted; the update path is where a stale id most plausibly arrives (the row was valid when the form was rendered). The blank cases matter because an empty string is not a forgeable id but would fail a naive existence lookup, producing a wrong error message on the most common optional-FK interaction. | FR-7 Verify (extend to three named cases) | Runtime: `POST /ui/chore/<id>` with `assigneeId=not-a-real-id` → 200 + field error, row unchanged; `assigneeId=""` on the optional FK → 303 with null stored; `memberId=""` on the required FK → 200 + required error. |
| R1-F4 | Security | high | FR-8 is scoped app-wide ("**In a tenant-scoped app** both the options query and the existence check filter the target…"), but scoping is resolved **per entity** — `render_web` builds a `scoped` set of the models that carry the owner column (L1322–1324) and threads `owner_field` per entity (L1100). Specify the 2×2 (owner scoped/unscoped × target scoped/unscoped) and require that a **scoped target** forces principal resolution on every route that renders or accepts that picker, even when the owning entity is unscoped. | The unscoped-owner × scoped-target cell is the leak the current wording misses: such a route has no `principal` dependency at all today, so the options query would either be unscoped (every tenant's labels and ids in the dropdown — precisely the §0 "new leak" this FR exists to close) or silently empty. It is also the cell the pilot schema will not exercise, so it will not be caught by the household regen. | FR-8 (replace the "In a tenant-scoped app" opening with the per-entity matrix); add a Risks-table row | Runtime: fixture with an **unscoped** Chore and a **scoped** Member; principal A's `/ui/chore/new` lists only A's Members, an anonymous request is refused rather than served unscoped, and A posting B's member id returns the same field error as a nonexistent id. |
| R1-F5 | Architecture | high | FR-3 fixes the surface at "**all four** routes that render `form.html`", but FR-7's "returning a field-level error on miss" adds a **fifth and sixth** render site (one per submit route) unless the FK errors merge into the same `errors` mapping consumed by the existing error branch. Make the invariant explicit in FR-3 ("exactly four `form.html` responses per entity; FK existence errors merge into the existing errors mapping and add no new render site") and give FR-7 a Verify that asserts it. | The generated error re-renders live *inside* `if errors:` (L1158–1163, L1206–1211) and have already returned by the point FR-7's check would run, so a literal reading of FR-7 produces two new response sites — each an independent chance to omit options and re-create exactly the empty-picker-on-error-path defect FR-3 was written to prevent. Stating the count as an invariant turns a review finding into a cheap structural assertion. | FR-3 (add the invariant sentence); FR-7 (add the no-new-render-site Verify) | Generator unit: count `"<e>/form.html"` template responses in generated `web.py` — exactly four per entity, and every one of them passes the options key. Runtime: a coercion error and an FK-miss error return through the same branch, both with populated options. |
| R1-F6 | Data | medium | Only FR-1 carries the qualifier "A **writable** scalar field"; FR-3 ("for each picker field") and FR-7 ("every picker field") are written over the unfiltered picker set. State that the picker set, the options helper, and the `_{e}_fk` map all derive from the **same** `_writable_fields(schema, entity, human_only)` set the form and `_{e}_rules` already use. | `form.html` inputs are already filtered by the owned-field policy (L797/817) and `_{e}_rules` likewise (L1080), so an FK column owned by `human_inputs.yaml` gets no widget — but an options helper and an `_{e}_fk` entry derived from `fk_targets` alone would still query the target on every render and existence-check a value the surface cannot submit. The "Owned fields — no new owned field is introduced" claim is only true if all three consumers share one filtered set. | "Owned fields" section (add the one-set sentence) and FR-3 / FR-7 wording | Generator unit: with a `human_inputs.yaml` owning `assigneeId`, the Chore form has no select, `_options_chore` has no `assigneeId` key, `_chore_fk` has no `assigneeId` key, and the output matches today's owned-field behavior. |

**Focus-weight coverage** — #1 relation trigger vs `*Id`: R1-S1 (plan-side; the hint predicate is still
suffix-keyed). #2 options on all four render paths: R1-F5 (+ plan R1-S3, R1-S6). #3 tenant scoping and
forged ids without touching shared `_coerce`: R1-F4, R1-F3 (+ plan R1-S5) — no suggestion here changes
`_coerce` / `_field_error` / `_{e}_rules`. #4 drift dep-set / no new manifest (FR-10): no suggestion
adds an input; plan-side R1-S2 and R1-S4 protect the claim. #5 deleted pickers stay deleted: nothing
below re-imports the `pickers:` manifest, a CLI flag, or an `"fk"` coercion kind.

**Endorsements** — none available: Appendix C had no prior rounds; R1 is the first round on this pair.

**Disagreements** — none available (no untriaged prior items).

#### Review Round R2 — Composer — 2026-08-14

- **Reviewer:** Composer
- **Date:** 2026-08-14 (UTC)
- **Scope:** Requirements-side (F-prefix) review of `FK_PICKER_REQUIREMENTS.md` **v0.4 (post-R1
  triage)**, weighted by `_crp/FOCUS_FK_PICKER.md`. Deeper-not-wider pass: R1's twelve accepted items
  are treated as settled and none is re-proposed. Newly grounded seams this round:
  `_WEB_HELPERS._form_errors` (L979–999, the empty-value skip at L992), `_coerce` (L929–947),
  `update_<e>`'s apply loop (L1212–1213), `edit_<e>`'s context (L1194–1196), the template's defensive
  context guards (L684–707, L765), `required` on the select widget (L648, L738–742), the blur `hx`
  attributes (L676–679), `guard404` (L1102–1104, applied at L1193), `_default_label_field` /
  `_LABEL_HEURISTIC` (L392–398), and `render_web`'s `scoped` set (L1322–1324). Onboarding archetype
  grammar and FR-FH-11 layout not re-litigated, per focus file.

**Executive summary**

- R1's structural findings hold. Nothing below re-imports the `pickers:` manifest, a `--picker*` flag,
  or an `"fk"` coercion kind, and nothing below touches `_coerce` / `_field_error` / `_{e}_rules`.
  The four-site invariant (R1-F5), the per-entity tenancy 2×2 (R1-F4), the non-submittable required
  placeholder (R1-F1), and deterministic ordering (R1-F2) are all taken as given.
- **The deepest gap is on the write side of FR-5's blank option.** `_form_errors` puts a key in `data`
  only when the raw value is non-empty (L992), and `update_<e>` applies **only** `data` (L1212–1213).
  So a submitted-empty optional FK is a **no-op on update**, not a null write: FR-5's "submits as unset"
  and FR-7's "stores null" are true on create and false on edit, and the route still returns 303 — the
  picker's `— none —` option promises a clear the write path never performs (R2-F1). This is *not*
  R1-F3 re-proposed; R1-F3's accepted Verify is the artifact this falsifies on one of its two paths.
- **Second: the stored FK value may not be in the option set.** `edit_<e>` scopes only the *owning* row
  (`guard404`, L1193); the FK **target** row is never checked, while FR-8 filters options to the
  principal. When the stored target is out-of-scope, deleted, or beyond FR-9's empty state, FR-6's
  "else the current record's value" resolves to nothing and the leading option wins — a **required**
  picker then makes the row permanently unsavable through the form, and an **optional** one displays
  `— none —` over a value that (per R2-F1) is still stored. FR-6 × FR-8 has an unspecified cell (R2-F2).
- **Third: the `options` context key is a cross-kind contract, and only its producer is specified.**
  The four render sites pass **three different context shapes** — `edit_<e>` sends `{"item": item}`
  alone (L1195) — which is exactly why every existing variable is guarded (`prefill is defined and
  prefill is not none`, L686; `errors is defined and errors`, L765). `form.html` (`htmx-form`) and
  `web.py` (`fastapi-web*`) are separately-owned, separately-hashed drift kinds that skip and
  hand-edit independently, so the halves can be at different versions. FR-3 fixes the producer and
  says nothing about the consumer (R2-F5).
- **Interfaces, unstated:** `required` is emitted on selects (L648, L739), so FR-5's disabled-placeholder
  required select is blocked **client-side** by native constraint validation — FR-5's required-error
  Verify is reachable at the TestClient layer but not in a browser, and FR-FH-11's `#err-<name>` slot
  never fills. The picker also inherits the blur `hx-post` triple (L676–679) unless something says
  otherwise (R2-F3).
- **Risks, unfiled:** FR-9 specifies the zero-row target; nothing bounds the many-row target. The
  emitted query is `select(Target)` + an `order_by` over an unindexed label column, run per picker
  field on every one of the four renders (twice per render for `Payment`), with no cap and — because
  typeahead is a Non-goal — no escape hatch (R2-F4).
- Non-goals and FR-10's dep-set claim still survive review; no suggestion below adds an input.

**Suggestions**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Risks | high | FR-5's submittable blank `— none —` and FR-7's "an optional FK submitted empty stores null" are achievable on **create** only. State the update-path truth and specify the clear: on `update_<e>` an empty picker value must actually null the column (merged alongside FR-7's existence check, i.e. outside `_form_errors`), **or** the inability to clear an FK through the picker must be named as a limitation with the 303 not reporting a save that did not happen. Add a Risks row for the class. | `_form_errors` adds a key to `data` only when `raw not in (None, "")` (L992), and `update_<e>` applies only `data` (`for k, v in data.items(): setattr(obj, k, v)`, L1212–1213). An optional picker submitted blank on edit therefore leaves the previous FK in place and still returns 303 `?updated=1` — the user selected `— none —`, saw a success flash, and nothing changed. Today's text input has the identical bug, but today it is invisible (nobody clears an id by hand); FR-5 *advertises* the clear as a first-class control, which converts a latent defect into a promised affordance that silently fails. It cannot be fixed inside `_form_errors` — that is a shared helper every generated app depends on and REQ §0 discovery 9 forbids touching it — so the fix has to live in the same merge-before-the-branch position FR-7 already occupies, which makes this a requirements decision rather than an implementation detail. | FR-7 (one sentence distinguishing create from update for the empty case) + a new `quality` Risks row; FR-5's Verify wording | Runtime: `POST /ui/chore/<id>` with `assigneeId=""` on a Chore that currently has an assignee → assert the stored column is `None` afterward (not the prior id), and that the response is 303. Negative control: the same POST on the create route already stores null. |
| R2-F2 | Security | high | FR-6's precedence and FR-8's scoping leave one cell unspecified: the **stored FK value is not in the option set** — because the target row is owned by another principal, was deleted, or the target is empty (FR-9) on an *edit* form. Specify it: the current value must round-trip (e.g. rendered as an additional, selected, non-clickable `— unavailable —` option carrying the stored id) so a save preserves it, and a required picker in that state must not lock the row. | `edit_<e>` guards only the **owning** row (`guard404`, L1193 — `item is None or item.<owner> != principal.id`); nothing validates the row's FK target, so a stored `assigneeId` pointing at a non-owned, deleted, or otherwise filtered Member is fully reachable. FR-8 then removes that row from the options, so FR-6's "else the current record's value" has no `<option>` to select and the leading option wins. Consequences split by optionality and both are bad: **required** → every subsequent save returns the required error, so the row becomes permanently un-editable through the form (a denial-of-edit reachable by another tenant deleting *their* row); **optional** → the form displays `— none —` while the column still holds the old id (see R2-F1), i.e. the form misreports stored state. This is the FR-6 × FR-8 intersection, not the FR-8 row-visibility question R1-F4 settled. | FR-6 (add the not-in-option-set branch to the precedence), FR-8 (state that scoping filters the *choices* without invalidating an existing stored reference), FR-9 (the empty state on an edit form must still render the stored value) | Runtime: two principals; A owns a Chore whose `assigneeId` points at **B's** Member (seeded directly). `GET /ui/chore/<id>/edit` as A → the select carries a selected option for the stored id and no other tenant's label; `POST /ui/chore/<id>` changing only the title → 200/303 with `assigneeId` **unchanged**. Same fixture with a required FK → the save succeeds rather than returning a required error. Zero-target edit form → the stored value still round-trips. |
| R2-F3 | Interfaces | medium | Name the layer that surfaces a required-picker error, and whether the picker participates in blur validation. `required` is emitted on the select, so FR-5's `<option value="" disabled selected>` placeholder is rejected by the browser's own constraint validation before any POST — FR-5's "returns a 200 form with a field-level required error" describes the API layer only. Either state that both layers hold (native bubble first, server error as the defense-in-depth backstop verified via TestClient) or drop `required` from the picker so FR-FH-11's `#err-<name>` slot is the single error surface. Likewise state explicitly whether the picker carries `hx-post="/ui/<e>/validate"`. | `required = " required" if _is_required(field) else ""` (L648) is interpolated into the select widget (L738–742), and the enum select already ships this way — so the picker inherits it. With a `value=""` option selected, an HTML5 `required` select blocks submission client-side, which means FR-5's stated user-visible outcome (a field-level error in the error slot, laid out per FR-FH-11) never occurs in a browser even though the TestClient assertion passes. That is a Verify that is green at the wrong layer. The blur triple `hx-post … hx-trigger="blur changed" hx-target="#err-<name>"` (L676–679) is the mirror question: if the picker keeps it, tabbing past an untouched required picker fires "This field is required." into the slot before the user has had a chance to choose, and FR-7's "blur `/validate` covers required-ness only" reads as if that were intended rather than incidental. | FR-5 (which layer owns the required message), FR-7 (one clause on whether the picker emits the blur attributes) | Rendered-template unit: assert the presence/absence of `required` and of the three `hx-*` attributes on the picker select, as a deliberate decision rather than inheritance. Runtime: the TestClient required-error assertion stays; add a note in FR-5's Verify that it exercises the server backstop, not the browser path. |
| R2-F4 | Risks | medium | FR-9 specifies the empty target; nothing specifies a **large** one. Add the cardinality assumption and its consequence: either a stated bound ("targets are expected to be small enumerable sets; above N rows the field falls back to today's text input", which stays presence-gated and adds no manifest) or an explicit Risks row accepting unbounded option counts. | The emitted query is an uncapped `select(Target)` with an `order_by` over the label column (no index is created for `_LABEL_HEURISTIC` columns, L392–398), executed **per picker field on every form render** — four render sites, and two queries per render for `Payment`'s two FKs. A 20k-row target therefore ships 20k `<option>` elements into every create page, every edit page, and every validation-error re-render, plus a full sort each time. Because typeahead, relation browsing, and client-side search are all Non-goals, there is no escape hatch inside v1: the requirement either bounds the case or knowingly accepts it. Note this interacts with FR-9 — the fallback-above-N behavior is the same "picker is presence-gated" shape FR-10 already relies on, so it costs no new machinery. | Risks table (new `quality`/`cost` row) + one sentence in FR-4 or FR-9 stating the cardinality assumption | Runtime: seed a target with N+1 rows and assert the specified behavior (either the text-input fallback, or a documented accepted degradation). Generator unit: assert the emitted query carries whatever bound the FR chooses, so the decision is visible in the artifact. |
| R2-F5 | Interfaces | medium | FR-3 specifies the **producer** of `options` but not the **consumer** contract. State that the template guards `options` the same way it guards `prefill` and `errors`, and that an absent `options` degrades (to the FR-9 empty state, or to the plain text input) rather than raising. | The four render sites pass three distinct context shapes — `new_<e>` sends `{item, prefill, created}` (L1134), the two error branches send `{item, prefill, errors}` (L1162, L1210), and `edit_<e>` sends `{"item": item}` **alone** (L1195). That is precisely why every existing context reference in the generated template is defensively guarded: `prefill is defined and prefill is not none` (L686, L700), `errors is defined and errors` (L765). A picker that iterates `options` without the same guard is a render-time failure, not a degradation — and the two halves of the contract are *separately owned drift kinds* (`htmx-form` for `form.html`, `fastapi-web` / `fastapi-web-forms` for `web.py`), independently skippable via the owned-file skip-hook, so they can legitimately be at different versions in a consumer repo: a customized (skipped) `form.html` beside a regenerated `web.py`, or the reverse. FR-3's invariant makes the producer side airtight and leaves the consumer side unstated, which is the same "slot exists, artifact never arrives" shape §0.2 cites Context-Correctness-by-Construction against — one level out, at the file boundary rather than the route boundary. | FR-3 (add the consumer clause) or FR-10 (as the presence-gated/degradation statement) | Rendered-template unit: render `form.html` with a context that omits `options` entirely and assert it produces HTML rather than raising, matching the FR's chosen degradation. Runtime: `edit_<e>`'s context shape is the narrowest of the four — assert the picker renders there. |

**Focus-weight coverage** — #1 relation trigger vs `*Id`: settled in R1 (R1-F1 area, R1-S1); nothing
here re-keys the trigger, and no suggestion reintroduces a suffix predicate. #2 options on all four
render paths: R2-F5 goes one level out from R1-F5 — the four *routes* are now invariant, but the
*template's* tolerance of a missing key across three different context shapes is unspecified.
#3 tenant scoping + forged ids without touching shared `_coerce`: R2-F2 (the scoped-out **stored**
value, the cell R1-F4's row-visibility matrix does not cover) and R2-F1 (the empty-value write path) —
both are deliberately placed *outside* `_form_errors` / `_coerce` / `_field_error` / `_{e}_rules`, none
of which any suggestion here modifies. #4 drift dep-set / no new manifest (FR-10): R2-F4's bound and
R2-F5's degradation are both schema-derived and presence-gated; no suggestion adds an input, a flag, or
a hash. #5 deleted pickers stay deleted: nothing above re-imports the `pickers:` manifest, a
`--picker*` flag, or an `"fk"` coercion kind.

**Endorsements** — none available. R1 was triaged in full (12/12 accepted, 0 rejected), so Appendix C
carries no untriaged leftovers to endorse.

**Disagreements** — one clarification, not a re-proposal. FR-7's Verify clause "given `assigneeId=""`
on the optional FK the response is a 303 with null stored" was merged from the accepted **R1-F3** and is
correct on the create route but unachievable on the update route as the shared write path stands
(`_form_errors` L992 → `update_<e>` L1212–1213). **R2-F1** reports that falsification and asks for the
missing update-path decision; it does not re-litigate R1-F3, whose create-path half stands.
