# Manifest Suggester — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-02
**Requirements:** `MANIFEST_SUGGESTER_REQUIREMENTS.md` (v0.1)
**Branch:** `feat/manifest-suggester` (worktree off `origin/main`).

---

## Planning discoveries (feed the reflection pass)

| What v0.1 assumed | What planning (code read) revealed | Impact |
|-------------------|-----------------------------------|--------|
| A schema-grounded **CRUD baseline** (a list/detail page per entity) is the core value (FR-MS-1) | **`pages.yaml` is for *owned, non-entity* content pages** — `pages_generator.py:1`: "Content-pages generator … non-entity pages from a `pages.yaml` manifest." **Entity CRUD is auto-generated from the schema by the cascade** (no manifest needed). A CRUD-per-entity baseline would duplicate what's already `$0`. | **FR-MS-1 reframed (big):** the suggester proposes **composite views** (dashboard/board/workspace over entities) + **non-entity content pages** — NOT entity CRUD. Schema-grounding = reference real entities *inside* composites, not enumerate CRUD. |
| Baseline + role-informed are two separate tiers | Both target the **same** non-obvious composite/content screens (a dashboard, a funnel, an admin page). The only `$0` baseline that isn't redundant is "a starter dashboard view over your primary entities." | **FR-MS-1/2 merge:** the value is the non-obvious screens; the `$0` baseline shrinks to a groundable starter composite, the paid role pass adds the rest. |
| "Reuse the panel infra" broadly (FR-MS-2/7) | **Partial:** `persona.Persona.ask(question, value_path)` and `routing.route/persona_matches(brief, value_path)` are **generic** (keyed on a `value_path`-like symbol) — REUSABLE. But `recommend.py`/`input_domains.py`/`recommend_apply.py` are **hard-bound to scalar value-input fields + the strict value parser**, and `grounding_guard` grounds against the *value corpus*, not schema entities — NOT reusable. | **FR-MS-2/7 narrowed:** reuse **persona + routing + roster + the recommend→review→approve *pattern***; the suggester has its **own** recommend/apply/grounding (manifest-shaped, schema-anchored). |
| The `manifest` kind may need a dest hint (OQ-2) | `_apply_manifest` takes **prose `source` only, never a path** (R1-F2); the server extracts + maps to `CONVENTION_PATHS` (round-trip-gated, no-clobber, all-or-nothing). | **OQ-2 resolved:** an approved screen → a `manifest` proposal with `source` = emitted prose. No new apply path, no dest hint. FR-MS-5 confirmed. |
| Prose grammar unknown (OQ-1) | Views = `view: <name>` sections with a `Kind ∈ {dashboard/board/workspace}` (`extract_views`); pages = `## Pages` rows (`extract_pages`); heading-delimited markdown. | **OQ-1 resolved:** the suggester emits this markdown; the extractor round-trips it. |
| A new "screens" roster role is needed (OQ-4) | The roster is generic (`role_id` + `answers_for` prefixes); routing matches `answers_for` to a `value_path` symbol. A design/PM persona with `answers_for` naming `views`/`pages` routes — **no new roster grammar**, just roster *content*. | **OQ-4 resolved:** model screens as a `value_path`-like symbol (`views`/`pages`); a design/PM persona owns it. |

**Net:** the loop killed the CRUD-baseline (redundant with `$0` codegen) and sharpened the capability to
**suggesting composite views + non-entity pages**, reusing persona/routing/the `manifest` kind but owning a
manifest-shaped recommend/apply/grounding.

---

## Approach & step map

### Step 1 — The schema-grounded candidate model (FR-MS-1/4, corrected)
- New `src/startd8/manifest_suggester/` package. `candidates.py`:
  - `schema_entities(root) -> EntityFacts` via `languages/prisma_parser` (primary/non-join models, key
    relations) — the grounding vocabulary.
  - `baseline_views(facts) -> list[ScreenCandidate]` — a `$0` starter **dashboard view** over the primary
    entities (a composite, groundable), emitted as `view: <name>` + `Kind: dashboard` prose. **No CRUD.**
  - `ScreenCandidate{kind: page|view, name, prose, entities_referenced, provenance}`.

### Step 2 — Grounding guard (FR-MS-4, schema-anchored — NOT the panel's)
- `grounding.py`: `ground(candidate, facts) -> Ok|Reject(reason)` — every `entities_referenced` must be a
  declared entity/field; reject unknown-entity candidates **before** the `manifest` apply's round-trip.

### Step 3 — Role-informed drafting (FR-MS-2, reuse persona/routing)
- `suggest.py`: reuse `stakeholder_panel.persona.Persona` + `routing.route` — route the "screens" symbol
  (`views`/`pages`) to its owning persona (bounded: owner or high-confidence `answers_for`, else skip). Ask
  the persona to draft non-obvious composites/pages **grounded in the entity facts** (the prompt carries the
  entity list). Parse the reply into `ScreenCandidate`s; run Step 2's grounding guard. Paid; `$0` baseline
  (Step 1) runs without it.

### Step 4 — Dedupe against the live manifest (FR-MS-3, OQ-6)
- Read the current `views.yaml`/`pages.yaml` (reuse the wireframe inventory / a small reader) → skip
  candidates whose name/slug already exists.

### Step 5 — draft → review → approve (FR-MS-7, mirror Teian pattern)
- `store.py` stages candidates out-of-band (session store, stale detection). CLI `cli_manifest_suggester.py`
  (or `startd8 screens`): `suggest` (baseline `$0` + optional `--roles` paid pass) · `review` (`$0` render) ·
  `approve`/`reject` → emits a **`manifest` proposal** (`source` = the candidate's prose) applied via
  `apply_proposal` at human privilege (FR-MS-5). Provenance marker on each (FR-MS-6).

### Step 6 — Surface the Red Carpet screens gap (FR-MS-8)
- When the advisor/wizard reports the screens gap, add a next-step/command pointing at `startd8 screens
  suggest` (discoverable at the moment of need). Presentation-only (glossary-plain per KICKOFF_UX).

### Step 7 — Tests
- Baseline: a schema → a groundable starter dashboard view (no CRUD pages); grounding guard rejects an
  unknown-entity candidate; dedupe skips an already-present screen; an approved candidate → a `manifest`
  proposal whose prose round-trips through `extract_views`/`extract_pages`; propose-confirm floor (no writes
  without approve); role routing bounded (un-owned screens symbol → skip, never a loose match).

---

## §7 Validation Strategy
- **No-CRUD-duplication:** the baseline emits composite views / non-entity pages only — a test asserts it
  never emits an entity-CRUD page (that's the cascade's job).
- **Schema-grounding:** a candidate referencing a non-existent entity is rejected before apply; an
  approved candidate's prose re-parses through the real extractor (round-trip).
- **Propose-confirm floor:** the loop never writes; every screen is a `manifest` proposal.
- **Reuse-not-fork:** the apply goes through the existing `manifest` kind (no new write path); a test
  asserts `PROPOSAL_KINDS` is unchanged.
- **Panel-isolation (NR-1):** the stakeholder-panel value pass is untouched; the suggester imports
  persona/routing but adds no value-domain.

## Risks
- **R1 — Baseline redundancy with `$0` CRUD gen.** Mitigation: the baseline is composites/non-entity pages
  only (the CRUD-duplication test).
- **R2 — Hallucinated entities from the role pass.** Mitigation: the schema grounding guard + the
  extractor round-trip (two gates).
- **R3 — Roster coupling.** Mitigation: reuse `persona`/`routing` only (generic); no dependency on the
  value-domain `recommend`/`input_domains`.
