# CRUD List Empty-State — Requirements

**Project:** startd8-sdk backend_codegen (HTMX entity list pages) · **Criticality:** medium
**Version:** 0.4 (post-CRP-lite R1)
**Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** startd8-python-cascade
**Audience:** end-user (a person who just read the welcome checklist and opened `/ui/<entity>`)
**Pairs with:** `CRUD_LIST_EMPTY_STATE_PLAN.md`
**Inherits standards:** `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` (its deferred v1 non-goal) · PC-13 (onboarding is content, not a modal) · PC-1 (audience-keyed content) · Sotto (presence-gated, hash-exempt Words seam) · `FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md` (`?created` flash contract) · `FORM_FIELD_LAYOUT_FR-FH-11.md` (clipboard-ledger tokens) · det-req-kit `BACKEND_ROUTING.md` UX rows (`#7 audience/presentation`, `#13 interactive-surface/rendering`)

---

## 0. Planning Insights (Self-Reflective Update)

> v0.1 assumed this feature needed a **new authoring surface** (a `list_empty:` section) whose copy
> would be embedded in the owned list template. Reading `htmx_generator.py`, `drift.py`,
> `onboarding_manifest.py` and the two dogfood apps falsified that on three counts: the copy already
> exists and is already threaded, the table itself (not the missing copy) is the defect, and a
> filtered-empty list is a different state that v0.1 did not distinguish. Seven corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| A new `views.yaml` `list_empty:` section is needed to carry the copy | `views.yaml` text is **already threaded** into `render_ui` (as `forms_text`, `assembler.py:130`) **and** into the drift renderer registry (`drift.py:126` `_renderers(forms_text=…)`), and `onboarding.empty_states` is already an entity→copy map, already strict-validated against the Prisma schema (`onboarding_manifest.py:76-85`, `onboarding_generator._validate`) | **OQ-1 resolved: no new YAML section.** FR-2 forwards `onboarding.empty_states`; zero new plumbing, zero new CLI flag, zero new hash input |
| Authored copy is *required* — an entity with no entry gets nothing | The CTA and heading are **fully determined by the schema** (`/ui/<e>/new`, the display title) — no authoring needed to fix the orphan | FR-1/FR-8: a deterministic panel renders for **every** entity, including apps with no `onboarding:` section at all. Authored copy is an *upgrade*, not a precondition |
| Add copy + a CTA **below** the empty table | With zero rows, `render_list_template` emits a `<thead>`-only `<table>` (`htmx_generator.py:504-520` — the `{% for %}` has **no `{% else %}`**). Verified live: `household-o11y/app/templates/member/list.html` renders a bare `name/role/notes` header row over an empty `<tbody>` | FR-1 **suppresses the table entirely** at zero rows and renders the panel in its place — the header-only table is pure noise, not a container to decorate |
| The list page has "no CTA" | It already has one — `<a href="/ui/{e}/new">New {entity}</a>` (`htmx_generator.py:511`). The defect is *emphasis and adjacency*, not absence | FR-4 promotes it into the panel as the primary action and forbids a **second** competing CTA in the zero-row state |
| Copy can be embedded in the owned `list.html` | `list.html` is a **schema-only 1-hash `htmx-list` kind**. Embedding views.yaml copy would make its header dishonest and force a new 2-hash kind, re-heading every generated app's list template — and every copy edit would trip `generate backend --check` | FR-3 applies **Sotto**: the copy lives in an untracked headerless fragment (`form_prose` / `view_prose` precedent), and the owned include line is **content-independent and unconditional**, so `list.html` stays schema-only and byte-stable w.r.t. views.yaml |
| Zero rows means "nothing added yet" | `items` is **post-filter** (`_list_query_lines`, `htmx_generator.py:1034-1067`). A facet/search miss also yields zero rows — showing "Add your first Member" there is a **lie**. `filters` in ctx is `dict(request.query_params)`, which is truthy after a `?created=` redirect, so it cannot be the test | **New FR-5:** `web.py` puts a deterministic `filtered` boolean in the list ctx computed from the entity's *declared* facet/search keys only; filtered-empty gets neutral "no matches" + clear, never the onboarding copy |
| Per-entity prose (`form_prose.yaml`) is a candidate home | `form_prose.yaml` is keyed to **form fields** and strict-validates targets against writable columns (`form_prose.py:101-108`) — list chrome has no valid key there. `view_prose.yaml`'s `empty:` key exists but is keyed by **composite view name** and is accepted only on a `detail-compose`; household's own `view_prose.yaml:7-10` records that the team's authored empty-state strings have **no home** for dashboard views | **OQ-1 rejects per-entity prose for v1.** A third copy home is speculative (Mottainai); deferred to Non-goals until a second consumer needs list copy that *diverges* from onboarding |

**Resolved open questions:**

- **OQ-1 → Reuse `onboarding.empty_states`; no new section, no new prose file.** Precedence is
  `onboarding.empty_states[Entity]` → deterministic schema-derived default. This is the only option
  that makes list copy and welcome-checklist copy **the same string by construction** rather than two
  strings free to drift; the other two both create a second authoring surface for one sentence.
- **OQ-2 → The panel replaces the table, it does not accompany it.** A `<thead>`-only table is cruft.
- **OQ-3 → Copy rides a hash-exempt fragment (Sotto), the skeleton stays owned.** Copy edits keep
  `generate backend --check` green; the one-time structural change to `list.html` is identical for
  every entity and every project.
- **OQ-4 → Filtered-empty is a distinct state** with its own neutral copy (FR-5).

### 0.1 Lessons-Learned Hardening (in-session; version held at 0.2 per session brief)

> Both recall surfaces were consulted with the `#7 audience/presentation` / `#13
> interactive-surface/rendering` keys. Recorded honestly:

- **Pattern-Catalog recall — empty.** `python3 -m contextcore.learning.pattern_catalog recall
  "requirement × audience/presentation" "code × audience/presentation" "code ×
  interactive-surface/rendering"` → `(none — browse fallback)`. Fell through to the markdown catalog
  as the adapter instructs.
- **Lesson recall — no applicable hit.** `contextcore lesson recall --project lessons-craft
  --task-type requirement --text "empty state list page CTA generated template copy reuse" --tag
  "audience/presentation" --top 6` returned six 0.70-tier lessons from unrelated domains
  (frontend testing, Supabase migration pipelines, card surfaces). None bear on this draft; nothing
  applied, nothing recorded as an application.
- **[PC-13 — Onboarding Is Content, Not a Modal]** (browse fallback) — forced the check "is this
  guidance page content or overlay chrome?" → the empty-state is an **in-flow content panel** in the
  list's own `{% block content %}`, no dialog role, no focus trap, no tour library (FR-1, NR-6).
- **[PC-1 — Audience-Keyed Content]** (browse fallback) — forced "is the copy resolved by graceful
  degradation, or re-authored per surface?" → the precedence chain in FR-2 is exactly PC-1's
  `(specific)→(base)` degrade, and it reuses the *existing* authored config rather than adding an
  N+1th one.
- **[Phantom-reference audit]** — every symbol this REQ names was grepped in the owning module before
  it was written; see §Reference audit. One phantom was caught and dropped: there is no
  `list_prose.yaml` and no entity-keyed `empty` key anywhere in the tree.

### 0.2 Design-Principle Hardening (in-session; version held at 0.2 per session brief)

> Filtered `PRINCIPLE-INDEX.md` §2 on the same two keys. Four principles fired; each changed the draft:

- **[Sotto]** (`code × audience/presentation` — the index's direct key match) — "does authored content
  ride a presence-gated, hash-exempt seam, byte-identical when absent?" → **rewrote FR-3.** The
  copy moved out of the owned template into an untracked headerless fragment, and the include line was
  made unconditional and content-independent so `list.html` never gains a views.yaml dependency. This
  deleted the proposed `htmx-list-forms` 2-hash artifact kind entirely.
- **[Mottainai]** — "does a later stage re-derive what an earlier stage already produced?" → **killed
  the `list_empty:` section (OQ-1).** The welcome checklist already produced entity→copy; the list page
  forwards that artifact instead of re-requesting the same sentence from the author.
- **[Hitsuzen]** (derive the determinable) — "is authoring being asked for something the inputs already
  fix?" → **added the deterministic default (FR-8) and moved the CTA out of the copy seam**
  (FR-4): href, label and heading are derived from the schema + display title, so the panel is
  correct with zero authoring. Also made `filtered` a computed boolean rather than an authored flag.
- **[Accidental-Complexity]** — "is a layer being added to compensate for a defect one general rule
  dissolves?" → **collapsed the design to one rule**: *every* entity list gets the same panel skeleton
  with a precedence-resolved sentence. No per-entity allowlist, no opt-in flag, no
  `enable_empty_states:` toggle. Non-goal NR-7 forbids reintroducing one.
- **[Genchi Genbutsu]** — grounded every claim against the tree, not the docs: the missing `{% else %}`
  was read in `htmx_generator.py`, the orphan was confirmed in the household app's *generated*
  `member/list.html`, and the drift threading was confirmed at `drift.py:275`.

### Reference audit (phantom-reference check, §0.1)

Every symbol this REQ names, grepped in its owning module before being written:

| Named | Exists? | Where |
|-------|---------|-------|
| `render_list_template` (no `{% else %}` branch) | yes | `src/startd8/backend_codegen/htmx_generator.py:490-520` |
| `render_ui(… forms_text …)` receives `views.yaml` | yes | `htmx_generator.py:1371-1400`; caller `assembler.py:130` |
| `_renderers(forms_text=…)` → `"htmx-list"` | yes | `drift.py:126`, `drift.py:275` |
| `parse_onboarding` / `empty_states` / `empty_state_map` | yes | `onboarding_manifest.py:37,43,76-85` |
| `_list_query_lines` (post-filter `items`) | yes | `htmx_generator.py:1034-1067` |
| list ctx `filters = dict(request.query_params)` | yes | `htmx_generator.py:1122-1123` |
| headerless-fragment precedent (`render_form_prose_fragments`) | yes | `htmx_generator.py:848-879` |
| unconditional tolerant include precedent (`_nav.html`) | yes | `htmx_generator.py:338` |
| `_BASE_STYLE` FR-FH-11 tokens | yes | `htmx_generator.py:165-305` |
| household `empty_states` for Member/Chore/Bill/Medication | yes | `household-o11y/prisma/views.yaml` |
| live orphan (header-only table) | yes | `household-o11y/app/templates/member/list.html` |
| `list_prose.yaml` / entity-keyed `empty:` key | **no** | phantom — dropped in §0.1 |

## Overview

When a cascade app's welcome checklist says "Add your first household member" and the user follows it
to `/ui/member`, they land on a page that renders a table header over nothing — no orientation, no
emphasized action. This adds a **generated list empty-state**: at zero rows the entity list renders a
content panel (heading, one sentence, primary create CTA) instead of an empty table. The sentence is
forwarded from the `onboarding.empty_states` the app already authored, falling back to a deterministic
schema-derived default, so the list page and the welcome checklist read as one voice without a second
authoring surface. Deterministic, `$0`, and correct for apps that declare no onboarding at all.
Deliberately later: FK picker widgets, welcome-page redesign, confirm-walk, and per-view dashboard
empty states.

Dogfood targets: `tests/fixtures/wireframe/prisma/views.yaml` (harness — already declares `empty_states`
for `Profile` and `Note`) and `~/Documents/dev/household/household-o11y` (lived — already declares all
four, and its `onboarding.continue_href` points at `/ui/member`, the orphaned page).

## Objectives

- O-1: A user who follows the welcome checklist to a zero-row list page finds orientation and one
  obvious next action — never a bare table header. Scoped to server-rendered page loads; the
  post-delete-to-zero HTMX swap is out of scope in v1 (FR-1 boundary, NR-9).
- O-2: List copy and welcome-checklist copy resolve from the same authored string **by construction**
  (one authoring surface, zero drift potential), and render as identical **text** on both surfaces —
  identity is asserted on rendered text, not on raw bytes, because the two paths escape at different
  times (FR-2).
- O-3: Zero new YAML sections, zero new CLI flags, zero new artifact kinds — `$0` and inert-safe.
- O-4: Editing empty-state copy never trips `generate backend --check`.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | The one-time `list.html` structural change re-renders every generated app's list templates, so any app pinned on `--check` reports drift until it regenerates | Change is identical and content-independent for every entity; call it out in the plan's rollout step and regenerate both dogfood apps in the same pass | high |
| quality | Showing "Add your first X" on a filtered-empty list is a factual lie to the user | FR-5 computes `filtered` from declared facet/search keys only (never from raw query params, which carry `created`) | high |
| quality | Scope creep into FK pickers / welcome redesign / dashboard empty states | Explicit non-goals NR-1..NR-5; a third copy home is NR-4 | medium |
| security | The panel echoes author-supplied copy into HTML, and the fragment is a **baked static file** — Jinja's autoescape (which protects the checklist path) does not apply to it | The generator `html.escape`s the authored sentence when writing `_list_empty.html` (FR-3), reproducing the checklist's render-time escaping at generate time; no request data enters the fragment | low |
| cost | A second copy home would double the surface for one sentence | Mottainai forward (OQ-1); revisit only on a real diverging consumer | medium |

## Profile

Declared profile: **internal**

## Functional requirements

> Code-comment labels use the `FR-LE-n` family (FR-1 ⇒ `FR-LE-1`), matching the in-tree
> `FR-CA` / `FR-DM` / `FR-FS` / `FR-FH` precedent; the doc IDs stay plain so the det-req extractor
> parses them.

- **FR-1 — Empty-state panel replaces the header-only table.** When an entity list renders zero
  items, `list.html` emits an in-flow empty-state panel (heading, copy slot, primary CTA) and
  suppresses the `<table>` entirely instead of rendering a `<thead>`-only shell. The panel is a
  **server-render-time state**, evaluated on a full page render only: deleting the last row swaps that
  `<tr>` for the flash `<tr>` (`htmx_generator.py:464-465`, `1232-1237`) and leaves the table standing,
  so the zero-row panel is reached on the next full GET of `/ui/<e>` — the delete swap is unchanged
  (NR-8) and gains no out-of-band panel swap (NR-9). Touches: htmx-list, htmx_generator.py. Verify: given the wireframe fixture with an empty `Profile` table,
  GET `/ui/profile` returns 200 whose body contains the panel copy and contains **no** `<table>`
  element; with one row it contains the table and no panel; and deleting the last row via the delete
  route still returns the flash `<tr>` unchanged, after which GET `/ui/<e>` shows the panel with no
  `<table>`. Serves: O-1
- **FR-2 — Copy forwarded from `onboarding.empty_states`, no new section.** The panel sentence
  resolves by precedence `onboarding.empty_states[Entity]` → deterministic default (FR-8), read
  from the `views.yaml` text already threaded to `render_ui`/`_renderers`. No new `views.yaml` section,
  no new prose file, no new CLI flag. The two surfaces escape at different times — the checklist puts
  the raw string in the Jinja ctx (`'copy': {copy!r}`, `onboarding_generator.py:53-64`) and autoescapes
  at render, while the fragment is baked at generate time (FR-3) — so identity is asserted on
  **rendered text**, not on raw bytes. Touches: onboarding.empty_states, htmx-list, htmx_generator.py. Verify: given household's
  `views.yaml`, the panel rendered at GET `/ui/member` shows exactly the sentence
  `Add your first household member to get started.`, and its rendered text equals the rendered text the
  welcome checklist shows for `Member`; with an authored value containing `&` or `<b>`, the two
  rendered texts still match. Serves: O-2
- **FR-3 — Copy rides a hash-exempt Words seam; the skeleton stays owned (Sotto).** The sentence is
  written to an untracked, **headerless** fragment `app/templates/<e>/_list_empty.html`, emitted for
  every entity and `{% include %}`d by the owned `list.html` with a **content-independent,
  unconditional** include line (the `base.html` `_nav.html` precedent) — so `list.html` remains the
  schema-only `htmx-list` kind with no views.yaml dependency and no new artifact kind. Because the
  fragment is baked HTML rather than a Jinja-autoescaped ctx value, the generator **HTML-escapes the
  authored sentence** (`html.escape`) when writing it, reproducing at generate time the escaping the
  checklist gets at render time. Touches: htmx-list, <e>/_list_empty.html, htmx_generator.py. Verify: editing an
  `empty_states` value and regenerating rewrites only `app/templates/<e>/_list_empty.html` — every
  owned file is byte-identical and `startd8 generate backend --check` exits 0. Serves: O-4
- **FR-4 — Primary create CTA lives in the panel, and is not duplicated.** The panel renders the
  create action as the emphasized primary control pointing at `/ui/<e>/new`, deriving its href and
  label from the contract (not from the copy seam); in the zero-row state the plain top-of-page
  `New <Entity>` link is not additionally rendered, so there is exactly one create affordance.
  Touches: htmx-list, /ui/<e>/new. Verify: GET a zero-row list page body contains
  exactly one occurrence of `href="/ui/<e>/new"`; a non-empty list page still contains the top link.
  Serves: O-1
- **FR-5 — Filtered-empty is a distinct state.** For entities declaring `filters:`, the list
  handler puts a `filtered` boolean in the template context, computed **only** from that entity's
  declared **facet** keys being present and non-empty, plus the search key `q` **only when that entity
  declares a non-empty `search:`** (`EntityFilter.search`, `filters_manifest.py:45-50`) — mirroring the
  query `_list_query_lines` actually builds, which emits the `q` branch only `if ef.search`
  (`htmx_generator.py:1059`). Never computed from raw query params, which carry `created`; and for a
  facets-only entity `?q=…` is **not** a filter. When `filtered` is true the panel renders neutral no-matches copy plus a clear-filters
  link and **suppresses** the onboarding sentence and the create CTA promotion. Touches: fastapi-web, htmx-list, filters, htmx_generator.py. Verify: on a filtered
  entity with zero stored rows, GET `/ui/<e>` shows the onboarding sentence; GET `/ui/<e>?<facet>=zzz`
  with rows stored shows the no-matches copy and a clear link, and does **not** show the onboarding
  sentence; and on a **facets-only** entity (no `search:`) with zero stored rows, GET `/ui/<e>?q=zzz`
  shows the onboarding sentence, not the no-matches copy — the mirror of the `?created=1` case.
  Serves: O-1
- **FR-6 — Drift parity, by *not* coupling.** Parity is achieved negatively: because the include line is
  content-independent (FR-3), `render_list_template` takes no `views.yaml` input, so the `htmx-list`
  drift renderer (`drift.py:275`) is **unchanged** — no onboarding spec is threaded into it, since a
  renderer that cannot consume the spec must not receive it. The headerless fragment is skipped by
  `--check` as a non-owned file. Touches: htmx-list, drift.py. Verify: `startd8 generate backend --check` exits 0 on the wireframe
  fixture and on regenerated household-o11y, both with and without an `onboarding:` section, and the
  `htmx-list` renderer entry in `drift.py` is byte-unchanged in the diff. Serves: O-3
- **FR-7 — Panel styling reuses the clipboard-ledger tokens.** Panel presentation is added to the
  existing owned `htmx-base` style block using the established FR-FH-11 CSS variables with literal
  fallbacks, so an unpolished app still renders a coherent panel and `startd8 polish` can override it.
  No new stylesheet, no new static asset. Touches: htmx-base, htmx_generator.py. Verify: the
  generated `base.html` contains the empty-state panel rules and every color reads through a
  `var(--…, <literal>)` fallback; `htmx-base` remains a schema-only kind. Serves: O-1
- **FR-8 — Deterministic default; inert-safe without onboarding.** With no `onboarding:` section,
  or an entity absent from `empty_states`, the fragment carries a schema-derived default sentence
  (built from the entity's display title) and the panel still renders with its CTA — the feature never
  requires authoring and never errors on an unlisted entity. Touches: <e>/_list_empty.html, htmx_generator.py. Verify: generating a project whose `views.yaml` has no
  `onboarding:` key emits a `_list_empty.html` per entity with the default sentence, and
  `generate backend --check` exits 0. Serves: O-3

## Non-goals

- **NR-1** Welcome-page / onboarding-checklist redesign — `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` owns
  that surface; this REQ only *consumes* its `empty_states` map.
- **NR-2** FK picker widgets (pilot P1-2 stays a later enhancement; raw ID text inputs are unchanged).
- **NR-3** The multi-step `confirm-walk:` archetype.
- **NR-4** A third copy home for list chrome (`list_prose.yaml`, an entity-keyed `view_prose` key, or a
  `form_prose` extension). Deferred until a consumer needs list copy that *diverges* from onboarding.
- **NR-5** Empty states for composite views / dashboards (`view_prose`'s `empty:` on non-`detail-compose`
  archetypes stays the documented §2.3 generator gap) and for the pages/admin surfaces.
- **NR-6** Any modal, overlay, dialog role, focus trap, or tour library (PC-13).
- **NR-7** An opt-in/opt-out toggle or per-entity allowlist for the panel — one general rule, applied
  uniformly (Accidental-Complexity).
- **NR-8** Changing the `?created` flash contract, the delete row-flash contract, or list pagination.
- **NR-9** An out-of-band panel swap on the delete-to-zero transition. The delete response stays the
  flash `<tr>` (NR-8); the panel is reached on the next full GET (FR-1). Revisit only if the reload gap
  is observed to matter in a real app.

## Owned fields

Only humans enter: `onboarding.empty_states.<Entity>` (the sentence) — already an owned field of
`ONBOARDING_ARCHETYPE_REQUIREMENTS.md`, forwarded here, not re-owned. The generator owns the panel
skeleton, the CTA href/label, the heading, the default sentence, and the no-matches copy.


## Contract projection

- **Backend:** `startd8-python-cascade`
- **Vocabulary home (cite):** `src/startd8/backend_codegen/htmx_generator.py` module docstring +
  `docs/design/python-contract-codegen/PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (artifact kinds and
  the owned/untracked split); onboarding grammar in `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` FR-2.

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| htmx-list | template | structure | `<e>/list.html`; gains the `{% else %}` panel + unconditional include; stays schema-only |
| <e>/_list_empty.html | fragment | words | Untracked, headerless, hash-exempt (Sotto); overwritten every regen |
| htmx-base | template | structure | `base.html`; panel CSS in `_BASE_STYLE`, var-with-fallback |
| fastapi-web | route | structure | `list_<e>` gains the computed `filtered` ctx key (FR-5) |
| onboarding.empty_states | manifest-section | words | **Consumed, not defined** — owned by the onboarding archetype |
| filters | manifest-section | structure | Read for declared facet/search keys only |
| /ui/<e>/new | route | structure | The panel's primary CTA target; already exists |
| htmx_generator.py | module | structure | `render_list_template` / `render_ui` / `_BASE_STYLE` |
| drift.py | module | structure | The `htmx-list` renderer registry entry — **unchanged** (FR-6 is a negative parity assertion) |

---

## Appendix A — Accepted (with where merged)

- **R1-F1 (high, Risks) — FR-1 bounded to the full-page render; NR-9 added.** FR-1 now states the panel
  is a server-render-time state and names the HTMX delete-to-zero transition (`htmx_generator.py:464-465`,
  `1232-1237`) as reached on the next full GET; O-1 carries the matching scope qualifier; NR-9 forbids an
  out-of-band panel swap so the fix cannot collide with NR-8's delete row-flash contract. Verify clause
  extended with the delete-then-GET sequence.
- **R1-F2 (high, Security) — generator escapes the baked sentence; O-2/FR-2 restated as rendered-text
  identity.** FR-3 now requires `html.escape` when writing `_list_empty.html` (the fragment is a static
  file, so Jinja autoescape — which protects `onboarding_generator.py:53-64` — does not reach it); FR-2's
  verify and O-2 assert **rendered-text** identity across the two surfaces rather than byte identity; the
  Risks `security` row's mitigation was rewritten, since "escaped exactly as the checklist escapes it"
  was not achievable by construction.
- **R1-F3 (medium, Interfaces) — FR-5's key set tightened.** `filtered` is computed from declared
  **facet** keys plus `q` **only when the entity declares a non-empty `search:`**, matching
  `EntityFilter.search` (`filters_manifest.py:45-50`) and the query `_list_query_lines` actually builds
  (`htmx_generator.py:1059`). A facets-only entity no longer reports `filtered=True` for a `?q=` the
  query ignores; verify gained that case as the mirror of `?created=1`.
- **Consequential sync from plan-side R1-S2 (accepted in the PLAN) — FR-6 restated as a *negative*
  parity assertion.** Not a new decision: FR-3's content-independent include already means
  `render_list_template` takes no `views.yaml` input, so threading the onboarding spec into the
  `htmx-list` drift renderer is dead plumbing and reads as evidence of a dependency Appendix B rejected.
  FR-6 and the `drift.py` row of the contract-projection table now say the renderer is unchanged, which
  is what the plan will implement.

## Appendix B — Rejected (with rationale)

- **A new `views.yaml` `list_empty:` section** — rejected (Mottainai / OQ-1). `onboarding.empty_states`
  already carries entity→copy, is already schema-validated, and its file is already threaded into both
  the generate and drift paths. A second section would let list copy and welcome copy drift apart —
  the exact single-source failure this corpus keeps filing.
- **Per-entity list prose (`form_prose.yaml` extension or `list_prose.yaml`)** — rejected for v1 (NR-4).
  `form_prose` is field-keyed and strict-validates against writable columns; `view_prose`'s `empty:` is
  view-name-keyed and archetype-gated. Adding a third copy home for one sentence is speculative.
- **A 2-hash `htmx-list-forms` artifact kind** — rejected (Sotto, §0.2). The hash-exempt fragment plus a
  content-independent unconditional include achieves the same coherence without re-heading every
  generated app's list templates or making copy edits trip `--check`.
- **Keeping the header-only table and adding copy below it** — rejected (OQ-2). A `<thead>`-only table
  is noise; the panel replaces it.
- **Gating the panel on a per-entity opt-in flag** — rejected (NR-7, Accidental-Complexity).

## Appendix C — Incoming review rounds

*v0.2 — Post-planning self-reflective update. 7 assumptions corrected, 1 requirement added (FR-5),
1 mechanism deleted (the `list_empty:` section and its 2-hash kind), 4 open questions resolved.
In-session §0.1/§0.2 hardening applied (2 patterns via browse fallback, 5 principles); version held at
0.2 per session brief. Not yet CRP-reviewed — CRP-lite (one Appendix-C round) is the S-size default.*

*v0.4 — Post-CRP-lite R1. R1 (Composer) filed 3 F-items; all 3 ACCEPTED and merged into the body
(FR-1 + O-1 + NR-9, FR-2/FR-3 + O-2 + Risks security row, FR-5). Dispositions recorded in Appendix A;
Appendix C left intact as filed. Plan synced at PLAN v0.4 (R1-S1..S3 accepted).*

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
| R1-F1 | Bound FR-1 to the full-page render; state the HTMX delete-to-zero transition; add NR-9 (no OOB panel swap) | R1 — Composer | Merged into FR-1 (server-render-time state + delete-then-GET verify), O-1 (scope qualifier), and new NR-9. Validate: delete last row → response is still the flash `<tr>`; then GET `/ui/<e>` → panel present, `<table>` absent | 2026-08-14 |
| R1-F2 | Escape the authored sentence when baking `_list_empty.html`; restate O-2/FR-2 as rendered-text identity | R1 — Composer | Merged into FR-3 (`html.escape` at generate time), FR-2 (rendered-text verify incl. `&` / `<b>` case), O-2, and the Risks `security` row. Grounded: checklist autoescapes via ctx at `onboarding_generator.py:53-64`; the fragment is a baked static file | 2026-08-14 |
| R1-F3 | Compute `filtered` from declared facets plus `q` only when the entity declares `search:` | R1 — Composer | Merged into FR-5 + its verify (facets-only entity, `?q=zzz` → onboarding sentence). Grounded: `EntityFilter.search` may be empty (`filters_manifest.py:45-50`); `_list_query_lines` emits the `q` branch only `if ef.search` (`htmx_generator.py:1059`) | 2026-08-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — Composer — 2026-08-14

- **Reviewer**: Composer
- **Date**: 2026-08-14 16:30:00 UTC
- **Scope**: CRP-lite, 1 round. Requirements-side (F-prefix) review weighted to the sponsor focus: filtered-vs-true empty (`query_params` trap), table suppression, checklist coherence without a double CTA, `htmx-list` staying 1-hash. Grounded against `htmx_generator.py`, `drift.py`, `onboarding_generator.py`, `filters_manifest.py`, and both dogfood `views.yaml` files.

**Executive summary**

- The v0.2 reflection pass is unusually well grounded — the §0 table, the reference audit, and Appendix B all hold up against the tree. All three F-items below are gaps the reflection pass did **not** reach, not re-litigation.
- **Blocking-ish gap (FR-1):** "renders zero items" is a *full-page-render* condition, but the only way a list reaches zero rows during a session is the HTMX row delete (`hx-swap="outerHTML"` → flash `<tr>`, `htmx_generator.py:464-465` / `1232-1237`). The panel therefore never appears on the transition that produces it; the doc is silent on this boundary.
- **Escaping asymmetry (FR-2/FR-3 ↔ risk table):** the checklist passes the copy through the Jinja ctx (`'copy': {copy!r}`, `onboarding_generator.py:53-64`) and autoescapes at render; the fragment bakes it into a static file at generate time. "Escaped exactly as the onboarding checklist escapes it" is not achievable by construction without an explicit `html.escape` in the generator, and O-2's *byte*-identity claim is what breaks first.
- **`q` over-claims declaration (FR-5):** `q` is only a live key when `search:` is non-empty (`filters_manifest.py:45-50`; `_list_query_lines` emits the `q` branch only `if ef.search`). A facets-only entity would report `filtered=True` for `?q=zzz` the query ignored — the same class of lie FR-5 exists to prevent.
- Corroborating note, filed as a suggestion on the plan side instead of here: **neither** dogfood `views.yaml` declares `filters:`, so FR-5 currently has no harness in either target.
- Areas considered and found already covered, so not filed: Ops (Step 6 rollout + the high-priority `--check` blast-radius risk row), Architecture (Sotto/`htmx-list` 1-hash invariant is stated correctly and grounded at `drift.py:275`), and the `?created` trap itself (FR-5 already names it).

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | high | Bound FR-1 to the full-page render and state the HTMX-delete transition explicitly. FR-1 says "When an entity list renders zero items" — but the row delete swaps one `<tr>` for a flash `<tr>` (`htmx_generator.py:464-465`, `1232-1237`), so deleting the last row leaves the table standing and the panel unrendered until a reload. Add to FR-1: the panel is a server-render-time state; the post-delete-to-zero transition is reached on the next full GET. Add a companion non-goal (NR-9) that the delete swap does **not** gain an out-of-band panel swap in v1, since NR-8 already protects the delete row-flash contract. | Without this the "never a bare table header" promise in O-1 is false for the single most common route to zero rows, and an implementer reading FR-1 literally may add an OOB swap that collides with NR-8. Naming it converts a silent hole into a stated boundary. | FR-1 (after "suppresses the `<table>` entirely…"), plus a new NR-9 in Non-goals | Test: delete the last row via the delete route, assert the response is still the flash `<tr>` (unchanged contract); then GET `/ui/<e>` and assert the panel is present and `<table>` absent. |
| R1-F2 | Security | high | Require the generator to HTML-escape the authored sentence when writing `_list_empty.html`, and restate O-2/FR-2 acceptance as *rendered-text* identity rather than byte identity. The checklist path puts the raw string into the template ctx (`onboarding_generator.py:53-64`) where Jinja autoescape applies at render; the fragment is a static file whose bytes are emitted by the generator, so an authored `&`, `<`, or quote is escaped on `/welcome` and raw in the fragment. | The risk table's mitigation — "Copy is escaped exactly as the onboarding checklist escapes it" — cannot hold by construction for a baked fragment, and the same divergence falsifies FR-2's byte-identity verify for any sentence containing an escapable character. Fixing it in the REQ is cheap; discovering it as a stored-XSS-shaped defect later is not. | FR-2 (verify clause), FR-3 (fragment definition), and the `security` row of the Risks table | Test: set an `empty_states` value containing `&` and `<b>`; assert the fragment contains the escaped form and that the rendered `/ui/<e>` panel text equals the rendered `/welcome` checklist text for that entity. |
| R1-F3 | Interfaces | medium | Tighten FR-5's key set: `filtered` is computed from the entity's declared **facet** keys, plus `q` **only when that entity declares `search:`**. FR-5 currently reads "declared facet/search keys", which the plan renders as "any declared facet key or the search key `q`" unconditionally — but `EntityFilter.search` may be empty while `facets` is not (`filters_manifest.py:45-50`), and `_list_query_lines` emits the `q` branch only when `ef.search` is non-empty. | For a facets-only entity, `?q=zzz` filters nothing yet would flip `filtered` to true, suppressing the onboarding sentence and showing "no matches" on a list that is genuinely empty — precisely the misreport FR-5 was added to prevent, arriving through a second door. It also keeps `filtered` exactly congruent with the query the handler actually built. | FR-5, the "computed **only** from that entity's declared facet/search keys" clause | Test: an entity with `facets:` but no `search:`, zero stored rows, GET `/ui/<e>?q=zzz` → body shows the onboarding sentence, not the no-matches copy. Mirror of the existing `?created=1` case. |

**Endorsements & Disagreements**

- None — Appendix C had no prior rounds; A and B are empty of reviewer items (Appendix B holds author-side reflection rejections, which R1 did not revisit).
