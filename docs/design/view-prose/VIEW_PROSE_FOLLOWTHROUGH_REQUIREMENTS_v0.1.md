# View Prose Follow-Through — Ecosystem Consistency, Drift-Recognition Completeness & Unlocked Enhancements — Requirements

**Version:** 0.4 (Phase-6 implementation reflection — Group A mostly pre-empted by the editors merge; FR-DRC-4/5 shipped)
**Date:** 2026-06-12 (v0.4, v0.3, v0.2, v0.1)
**Status:** Group A ✅ (FR-DRC-2/3 pre-shipped; FR-DRC-1 superseded; FR-DRC-4/5 done on `feat/drift-recognition-group-a`). Groups B-G open.
**Owner:** `startd8-sdk` (SDK-internal + kickoff templates) · touches consumer `strtd8` docs
**Pairs with:** `docs/design/view-prose/VIEW_PROSE_FOLLOWTHROUGH_PLAN_v0.1.md` (the planning pass whose
code-grounded findings drove this v0.2).
**Trigger:** the View Prose capability shipped to `main` 2026-06-12 (`0e8d08fb`; full key-set
title/intro/empty/success/error/controls). Building it (a) **proved** reusable patterns and (b)
**surfaced** that several ecosystem surfaces don't yet know `view_prose.yaml` exists, and that the
deterministic skip-hook silently drops manifest inputs.
**Related:** `docs/design/view-prose/VIEW_PROSE_PLAN_v0.1.md` (the shipped capability, v0.5),
`strtd8/docs/USER_FACING_CONTENT_REQUIREMENTS.md` (v0.9, the consumer contract),
`docs/design/kickoff/templates/REQUIREMENTS_TEMPLATE.md` + `REQUIREMENTS_AND_PLAN_FORMAT.md`,
`strtd8/docs/v2/ASSEMBLY_INPUTS.md`, the **editors-archetype** planning (which independently surfaced
drift bugs A-2/A-3 below; this doc consolidates them).
**SDK citations are `verify-at-home`** (drawn from a read of `main` at `0e8d08fb`).

---

## 0. Why this exists (the observed state)

Shipping View Prose was the SDK's *fourth* hash-exempt prose manifest (`pages.yaml`→`*.md`,
`ai_passes.yaml`→`*.md`, the parked `view_prose.yaml`, now live `view_prose.yaml`→fragments). Two things
became undeniable:

1. **The manifest ecosystem has a recognition hole.** The "$0 deterministic skip" thesis depends on the
   prime-contractor skip-hook recognizing a manifest-derived owned file as in-sync. But the skip-hook
   verifies with **schema only** — it drops every other manifest (`views.yaml`'s `forms:`, `pages.yaml`,
   `display.yaml`, `completeness.yaml`, `human_inputs.yaml`, `ai_passes.yaml`, and now `view_prose.yaml`).
   So manifest-derived owned files **fall through to the LLM** — paying cost and re-introducing
   non-determinism for files the SDK can generate for $0. View Prose adds *more* files to this fragile
   path, so it both **necessitates** and is partly **blocked** by the fix.

2. **The ecosystem doesn't know `view_prose.yaml` exists.** The assembly-inputs inventory describes the
   *overruled* design; the wireframe pre-gen readout omits view-copy coverage; the capability index has
   no entry; the kickoff requirements template has no place to declare view copy. Each is a small
   consistency debt that, left alone, drifts the docs from the shipped reality.

Separately, the build **proved** patterns worth elevating (a prose-gated additive-manifest principle) and
**unblocked** quick wins (the fragment mechanism now exists to absorb scattered hardcoded copy).

This doc groups the work into FR families. **Group A** (drift-recognition) is the architectural centerpiece;
**Group G** (view-copy extraction) is the highest *value* unlock — both surfaced/sharpened by the planning
pass below.

---

## 0.5 Planning Insights (self-reflective update, v0.1 → v0.2)

> The planning pass (`…_PLAN_v0.1.md`) read `manifest_extraction/`, `backend_codegen/drift.py`, and
> `wireframe/` at `0e8d08fb`. It overturned the single biggest v0.1 assumption and surfaced a quick win
> that was invisible beforehand. SDK citations are `verify-at-home`.

| v0.1 assumption | Planning discovery | Impact |
|---|---|---|
| FR-FMT-1 = "add a View-copy section to the template" (a docs edit) | **The requirements doc is a deterministic ($0, no-LLM) manifest *compiler*** (`manifest_extraction/extract.py`) that emits **6 of the 8** manifests — **not** `view_prose.yaml` (nor `display.yaml`). The view-copy *consumer* (`parse_view_prose`) exists; the *producer* (extractor) does not. | **FR-FMT-1 PROMOTED to a new Group G** — *author view copy in the reqs doc → derive `view_prose.yaml` ($0)*. A real capability, not a doc edit. |
| (not seen) | **`Empty state:` is already authored** in every `### View:` block but maps to `not_extracted(generator-gap)` (`extractors.py:241-245`) — a dead-end. The view_prose `empty` key + renderer now exist. | **New quick win (FR-VCE-2):** connect the existing-but-ignored authoring → `view_prose.yaml` `empty:`. Both ends exist; only the extractor is new. |
| (not seen) | The derivation emits **6/8** manifests; `view_prose.yaml` and `display.yaml` are both un-compiled. | New theme: **manifest-extraction parity** (FR-VCE-4 — `display.yaml` is the sibling gap). |
| Group A skip-hook needs building | The backend provider **already has** `_read_anchored()`/`_read_manifest()`/`_read_human_inputs()` — **unused** by `is_in_sync()`; `check_drift` already kind-routes + has the full signature. | **FR-DRC-3 is "wire up existing helpers,"** not new plumbing — confirms the small-thread-through verdict. |
| FR-DRC-2 = add flow kinds to `_FORMS_KINDS` | Flow kinds are in **no** kind-set AND **no** renderer map; a kind needs **both**. Flows are distinct from forms. | FR-DRC-2 reframed as a **new `_FLOWS_KINDS` family** (kind-set + checker + renderers). |
| FR-FMT-2 (lifecycle conventions) might be a parser concern | **Zero** machine consumption — the extractor ignores any non-anchored section. | **FR-FMT-2 narrowed** to a pure format-doc edit (decoupled from FR-FMT-1). |
| FR-DP-2 = extract a shared fragment primitive | The 3 mechanisms are **intentionally divergent** — AI prompts are **runtime-loaded**, not generate-time fragments. | **FR-DP-2 DROPPED** (folds into FR-DP-1 as "document the pattern + the runtime variant"). |
| FR-WCI-2 (content rollup) bundled with FR-WCI-1 as a quick win | FR-WCI-1 is quick (catalog + `Status` model exist); the **rollup** needs a new `ContentCoverageStats` + a `--json` schema bump = **medium**. | **Split FR-WCI-1 (quick) from FR-WCI-2 (medium).** |

**Resolved open questions:**
- **OQ-2 → resolved (no new plumbing).** The backend `ProviderContext` already lets the provider resolve
  every manifest via conventional `prisma/` paths (the unused `_read_anchored` helper); FR-DRC-3 is a
  small thread-through.
- **OQ-4 → resolved (drop the extraction).** FR-DP-2's shared primitive is not worth it — the mechanisms'
  time-of-binding differs fundamentally (generate-time fragments vs runtime prompt load). Document only.

---

## 1. Objectives

- **O-1** — The prime-contractor skip-hook recognizes **every manifest-derived owned file** as
  $0-deterministic when in-sync, so no such file falls through to the LLM. *(target: 0 manifest-derived
  files mis-classified; measured by a coverage test, FR-DRC-5.)*
- **O-2** — Every ecosystem surface that enumerates manifests (`ASSEMBLY_INPUTS.md`, wireframe catalog,
  capability index, kickoff template) lists `view_prose.yaml` accurately.
- **O-3a** — *(NEW — the planning unlock)* Authored view copy in the requirements doc is **deterministically
  compiled to `view_prose.yaml`** ($0, no LLM), closing the kickoff→manifest loop for the words layer and
  lighting up the already-authored `Empty state:` field. *(target: the derivation emits 8/8 manifests, not 6/8.)*
- **O-3** — The requirements/plan template + format codify the now-proven reflective-loop lifecycle and the
  Words/Structure classification, so future manifest features are authored consistently.
- **O-4** — The prose-gated additive-manifest pattern is a named, documented design principle with a single
  shared rendering primitive (de-duplicating the 3 hand-rolled copies).
- **O-5** — The fragment mechanism is reused to absorb the remaining hardcoded user-facing literals
  (low-risk quick wins).

---

## 2. Non-goals

- **Not** re-litigating the View Prose design (shipped; this is *follow-through*).
- **Not** a kickoff *manifest scaffolder* that auto-emits starter `pages.yaml`/`view_prose.yaml`/… for a
  new app — desirable but a separate, larger capability (noted as OQ-3).
- **Not** changing the drift *hash* model (whole-text per manifest stays); this only fixes which manifests
  the recognition path **threads**.
- **Not** adding new view-copy *keys* (the key-set is complete); group E only *relocates* existing literals
  and *extends* `empty`'s archetype reach.
- **No** new LLM passes — every item here is deterministic ($0) or docs.

---

## 3. Functional Requirements

### A. Drift-recognition completeness (capability-integration architectural — the critical group)

> **✅ IMPLEMENTATION STATUS (2026-06-12, Phase-6 reflection) — most of Group A was ALREADY SHIPPED.**
> Between this doc's CRP grounding (`0e8d08fb`) and implementation, the **editors-archetype merge**
> (`f8b6a812` FR-ED-15, `31ad3b85` FR-ED-16; main now `02920600`) landed and **independently fixed
> FR-DRC-2 and FR-DRC-3** via a *"pass-all-manifests"* design (the backend provider threads **every**
> manifest always; schema-only kinds ignore them — simpler than, and superseding, FR-DRC-1's
> `KIND_TO_INPUTS` map). It even shipped `test_skip_hook_manifest_recognition.py`. So:
> - **FR-DRC-2 — DONE** (flow kinds in `_FORMS_KINDS` + `_forms_renderers()`, `drift.py:72-78,557-559`).
> - **FR-DRC-3 — DONE** (`owned_file_in_sync` + `PydanticSQLModelProvider.is_in_sync` thread all manifests).
> - **FR-DRC-1 — SUPERSEDED** (the explicit map is unnecessary under "pass-all"; **do not build it** —
>   redundant complexity).
> - **FR-DRC-4 — IMPLEMENTED** (`feat/drift-recognition-group-a`, `65c82ad0`) — the **view** provider was
>   the one genuine remaining gap (it threaded `view_prose.yaml` but not `display.yaml`).
> - **FR-DRC-5 — IMPLEMENTED** (same branch) — a **provider-level** recognition lock
>   (`test_skip_hook_provider_recognition.py`), verified load-bearing (it fails on the pre-FR-DRC-4 code).
>
> The skip-hook (`is_deterministically_provided` → each provider's `is_in_sync`) and the in-CLI
> `--check` are **two paths to the same drift logic**. The remaining FRs below are retained as the
> record of what was specced; only FR-DRC-4/5 needed building.

- **FR-DRC-1 — A per-recognition-unit input-set declaration (LOAD-BEARING for 3+5; rescoped per R1-F1/F3).**
  **Code-verified (R1):** only the **backend** provider has discrete embedded *kinds* (`drift.py:47-74`); the
  other 4 deterministic providers are **kindless** — frontend = schema-only, scaffold = marker + `app.yaml`,
  polish = `POLISH_MARKER` + **path-suffix** dispatch, view = marker + whole-set render. So a single
  `KIND_TO_INPUTS` dict cannot be the SSOT for all 5. Define **two** layers: (a) a backend `KIND_TO_INPUTS`
  map (kind → required manifests, implicit today in the `_*_KINDS` sets); (b) a **provider-level
  `declared_inputs`** for the 4 kindless providers (schema-only / `app.yaml` / theme manifest /
  schema+views+view_prose+display). Both the CLI `--check` and the skip-hook read these. **Fail-closed
  (R1-F3):** a backend owned kind absent from `KIND_TO_INPUTS` MUST verify as not-in-sync (preserve the
  current unknown-kind `tampered` posture, `drift.py:600-606`) — never silently schema-only-verify. *Verify:*
  a synthetic backend kind not in the map → skip-hook returns not-in-sync; each provider exposes a non-empty
  declared input-set both call sites read.
- **FR-DRC-2 — New `_FLOWS_KINDS` family (BUG A, verified; reframed).** `fastapi-flow` / `flow-shell`
  (`flow_generator.py:30/112`, emitted with a `forms-sha256` header) are in **no** kind-set **and no**
  renderer map — and a kind needs **both** to be drift-checkable. Add a `_FLOWS_KINDS` + `_flows_renderers()`
  (`render_flow_router`/`render_flow_shell`) + `_check_flows_drift()` (schema + views.yaml), routed in
  `check_drift` — parallel to forms, not overloaded into `_FORMS_KINDS`. *Verify:* a flows app whose
  `views.yaml` changes reports `stale`; an unchanged flows app reports `in_sync` on `generate backend --check`.
- **FR-DRC-3 — Backend skip-hook threads the kind's manifests by wiring up EXISTING helpers (BUG B,
  verified; smaller than feared).** `owned_file_in_sync()` (`drift.py:325-339`) passes only `schema_text`;
  the backend provider **already has** `_read_anchored()`/`_read_manifest()`/`_read_human_inputs()`
  (`provider.py:62-101`) but **doesn't call them**. `is_in_sync` must read the file's kind, resolve the
  manifests `KIND_TO_INPUTS` declares (via those helpers + conventional `prisma/` paths — no new plumbing,
  OQ-2 resolved), and forward them to `check_drift` — exactly as the CLI does (`cli_generate.py:280-290`).
  **Behavior-change gate (R1-F4/S2):** this is a *correctness fix that shifts cost* — files that today
  **falsely** `$0`-skip (a `forms:`/AI/pages change with an unchanged schema) will correctly re-classify to
  not-in-sync → LLM. With ~9 downstream repos tracking the live branch, ship it behind a one-release flag or
  with a changelog/migration note documenting the one-time $-delta; do **not** land it silently.
  *Verify:* a `fastapi-web-forms`/`htmx-created` file from a non-trivial `forms:` section is recognized as
  `$0`-in-sync by the skip-hook (today it falls through to the LLM); a pre-fix in-sync forms file with a
  *changed* `forms:` reports not-in-sync after the change (documented as expected).
- **FR-DRC-4 — View provider threads display + view_prose (BUG C + consistency).**
  `CompositeViewProvider.is_in_sync` (`provider.py:25-37`) threads `view_prose_text` but **not**
  `display_text`; the CLI threads both (`cli_generate.py:466-467`). Add `display_text` resolution (~3 lines,
  mirroring view_prose) and pass it to `views_in_sync` (already accepts it). *Verify:* a view file whose only
  changed input is `display.yaml` reports not-in-sync via the skip-hook; unchanged ⇒ in-sync.
- **FR-DRC-5 — Regression lock across ALL 5 providers (enumeration source specified per R1-F2/F10).** The
  lock must enumerate from each provider's **own recognition surface** — backend = `_*_KINDS` ∪ `_renderers()`
  keys; the 4 kindless providers = their `owns()`-recognized artifact set (polish's path-suffix partials +
  stylesheet/static relpaths; scaffold's `app.yaml`-derived set; frontend's schema-only set; view's owned
  set) — and assert each provider contributes a **non-empty** set (else the lock passes **vacuously** — the
  exact failure class it exists to prevent). It asserts the skip-hook resolves the inputs FR-DRC-1 declares.
  **Carve-out note (R1-F10/OQ-1):** if Group A becomes its own PR, the lock is a **shared** test artifact
  asserting against providers (view/polish) Group A doesn't otherwise modify — it lives in a shared
  `tests/unit/` path, not duplicated. *Verify:* the test fails if a future kind/artifact is added whose drift
  inputs the skip-hook doesn't thread, and fails if any provider's enumerated set is empty.

### G. View-copy extraction — author copy in the reqs doc → derive `view_prose.yaml` ($0) *(NEW; the planning unlock)*

> The reqs doc is a deterministic ($0, no-LLM) manifest compiler (`manifest_extraction/`) that emits 6 of
> the 8 cascade manifests; `view_prose.yaml` is one of the two it doesn't. The *consumer*
> (`parse_view_prose`) is shipped — only the *producer* (extractor) is missing. This group closes the loop
> and lights up an already-authored, currently-dead field.

- **FR-VCE-1 — `extract_view_prose()` in `manifest_extraction`.** Add an extractor that parses per-view
  copy keys from each `### View:` block (the block already uses the `- Key: value` grammar), wired into the
  candidate set (`extract.py:145-158`) and the round-trip table (`extract.py:162-175`) calling the
  **existing** `parse_view_prose(text, known_views=…)` so a bad copy block fails **at ingestion** (loud,
  FR-WPI-4), not at `generate views`. **`known_views` source (R1-F5/S3, code-verified):** the round-trip's
  `known` is `graph.all_model_names()` (`extract.py:161`) — **model** names; `parse_view_prose` needs **view**
  names and the graph has **no `all_view_names()`**. So FR-VCE-1 MUST source view idents from the extracted
  **`views.yaml` candidate** (a named cross-candidate dependency — views before view_prose, OQ-6) or add a
  `Graph.all_view_names()`; *ordering alone does not supply them*. **Escaping contract (R1-F9):** view copy is
  author text that becomes page HTML via the untracked fragment — the extractor MUST honor the renderer's
  per-archetype escaping (markdown for `intro`, escaped-literal for `title`/`empty`/labels, whitelist for
  `success`/`error`), never emit raw author text into a raw-include slot. *Verify:* a reqs doc with view copy
  yields a valid `view_prose.yaml`; view copy referencing an unknown view name fails ingestion; a value
  containing `<`/`{{ }}` renders escaped per the target archetype.
- **FR-VCE-2 — Close the `Empty state:` dead-end (the quick win; archetype-filtered per R1-F6/S4).
  ✅ IMPLEMENTED (`feat/view-copy-extraction`, `1e954fd2`) — with a Phase-6 correction.**
  `Empty state:` is **already authored** in every `### View:` block but mapped to `not_extracted(generator-gap)`.
  Route it to `view_prose.yaml` `empty:` **only for model-scoped detail-compose views**, and **keep silently
  dropping it (no error) on every other archetype** — preserving back-compat (the renderer raises `ValueError`
  on `empty` off-archetype, `renderers.py:~1853`).
  > **⚠️ Phase-6 finding (implementation):** the quick win was a **no-op as-planned** — `extract_views` never
  > emitted `scope`, so **no** kickoff-derived view was a model-scoped detail-compose, and every `Empty state:`
  > would silent-drop (the only valid surface didn't exist). **Fix shipped:** `extract_views` now emits
  > `scope: model` from a new `Scope:` key (template FR-FMT-1), which *also* reaches `views.yaml`. Without this
  > prerequisite the `empty` route delivers zero value; the celebrated quick win required unblocking it first.
  *Verify:* a board view with `Empty state:` extracts with **no** `empty:` and **no** error; a `Scope: model`
  detail-compose with `Empty state:` produces `empty:`. (Both pinned in `test_view_prose_extraction.py`.)
- **FR-VCE-3 — Per-archetype validity is end-to-end (no new validator).** The extractor emits the keys; the
  **shipped renderer already rejects** archetype-invalid combinations (`renderers.py:1862-1881`:
  `empty`→detail-compose-model, `success`/`error`/`controls`→import-flow). *Verify:* `empty` authored on a
  computed-panel fails the round-trip at ingestion (reusing the renderer's loud-fail).
- **FR-VCE-4 — Manifest-extraction parity (`display.yaml` sibling) — GATED on a feasibility table (R1-F7/S6).**
  The same gap exists for the structure layer (derivation doesn't emit `display.yaml`). **But `display.yaml`
  is structure/bindings (column order, FK label resolution, `format`), not flat words** — it may need richer
  authoring than the `### View:` grammar carries, so it is **not** symmetric effort with view_prose and must
  **not** ride FR-VCE-1's coattails. Prerequisite: a **field-derivability table** enumerating which
  `display.yaml` fields the reqs grammar can author vs. which need new authoring. If any required field needs
  new authoring, FR-VCE-4 **splits to its own increment/OQ**. *Verify:* the table exists; `generate schema
  --with-manifests` emits `display.yaml` only for the derivable subset. *(Separable; lowest urgency.)*

### B. Kickoff inputs & assembly-inputs consistency

> **✅ Group B DONE (2026-06-13).** SDK-home docs committed on `feat/view-prose-group-b`: FR-KIN-2
> (`KICKOFF_INPUTS_EXPLAINED_TEMPLATE.md` gained an explicit **Words/Structure split** naming
> `view_prose.yaml` under Words) + FR-KIN-3 (`ASSEMBLY_INPUTS_TEMPLATE.md` gained a `view_prose.yaml`
> row + machine-readable YAML entry). FR-KIN-1 (the strtd8 instance `docs/v2/ASSEMBLY_INPUTS.md`)
> corrected in the **strtd8 repo** — left for the user to commit there (separate repo).

- **FR-KIN-1 — Correct the `ASSEMBLY_INPUTS.md` view_prose entry. ✅ DONE (strtd8-side).** The strtd8 inventory still describes
  the *overruled* design ("→ `views.yaml` `prose:` … parked until strict-parse supports the `prose:` key").
  Replace it with the shipped reality: a **standalone `prisma/view_prose.yaml`** consumed by
  `generate views --view-prose`, hash-exempt (rendered to untracked fragments), full key-set
  title/intro/empty/success/error/controls. *Verify:* the entry's "Drives" column reads
  `generate views --view-prose` and the lifecycle column reads "outside the drift hash".
- **FR-KIN-2 — Kickoff inputs taxonomy classifies view_prose explicitly.** Confirm/keep the
  `KICKOFF_INPUTS_EXPLAINED.md` taxonomy places `view_prose.yaml` on the **content-prose / hash-exempt /
  author→approve** side (not the structural/hashed side), beside `app/pages/*.md`. *Verify:* the taxonomy's
  Words/Structure split names `view_prose.yaml` under Words.
- **FR-KIN-3 — The `ASSEMBLY_INPUTS_TEMPLATE.md` carries a view_prose row.** The reusable inventory
  template (SDK kickoff) gains a placeholder row for `prisma/view_prose.yaml` so every new project's
  inventory includes it. *Verify:* the template lists view_prose with `<status>` placeholder.

### C. Requirements format & template updates

> **✅ Group C DONE (2026-06-13, `feat/view-prose-group-c`).** FR-FMT-1 (format-doc half — the View
> copy keys' grammar + `[consumed by: extraction → view_prose.yaml]` annotation; the template half
> shipped earlier with Group G), FR-FMT-2 (new **Part D — Document lifecycle conventions**: §0 Planning
> Insights / version lineage / "what changed in vX" / Implementation Reflections / Appendix A/B/C CRP
> scaffold — pure human convention, zero parser risk; **REQUIREMENTS_TEMPLATE.md** ships the empty §0 +
> Appendix scaffolds), FR-FMT-3 (**Words vs Structure** classification rule citing display.yaml=structure /
> view_prose.yaml=words + the SOTTO link — this also closes **FR-DP-1's deferred Words/Structure
> backlink**), FR-FMT-4 (**$0-codegen acceptance-criteria checklist**, referenced from the Views copy keys).

- **FR-FMT-1 — The template's "View copy" keys (the *authoring surface* for Group G). ✅ DONE.** Add the per-view
  copy keys to the `### View:` block in `REQUIREMENTS_TEMPLATE.md` (title/intro/empty/success/error/controls,
  parallel to the existing `Empty state:` line) + a `[consumed by: extraction → view_prose.yaml]` annotation
  in `REQUIREMENTS_AND_PLAN_FORMAT.md`. **Pairs with FR-VCE-1** (the extractor that consumes them) — together
  they make view copy authorable-then-derivable. *Verify:* the format doc lists the keys' exact grammar under
  the View block; FR-VCE-1's extractor reads them.
- **FR-FMT-2 — Codify the reflective-loop lifecycle conventions (PURE doc — no parser, planning-confirmed).**
  The lifecycle is **human convention only** (the extractor ignores any non-anchored section), so this is a
  format-doc + scaffold edit with zero parser risk. Make first-class in `REQUIREMENTS_AND_PLAN_FORMAT.md`:
  a `§0 Planning Insights` table (v(n-1)→v(n) discoveries), the `Appendix A/B/C` CRP review-log scaffold,
  the "What changed in vX" callout convention, the version/date *lineage* header, and an
  **"Implementation Reflections"** convention (Phase-6 findings fed back, as v0.7→v0.9 did). *Verify:* the
  format doc names each convention with an example; the template ships the empty scaffolds.
- **FR-FMT-3 — Add the Words/Structure classification rule.** The format gains a one-paragraph rule: any
  *new file-shaped input* is classified **hashed-structure** (a `views.yaml` section / standalone hashed
  manifest) **or** **hash-exempt-prose** (a standalone file rendered to an untracked fragment), and routed
  accordingly. *Verify:* the rule cites the shipped split (display.yaml=structure, view_prose.yaml=words).
- **FR-FMT-4 — Add the `$0`-codegen acceptance-criteria checklist.** Capture the recurring ACs proven by
  View Prose as a reusable checklist for any deterministic-manifest feature: **byte-identical-when-absent**,
  **fail-closed on a malformed manifest**, **drift-stability** (editing hash-exempt content never trips
  `--check`), **strict loud-fail parse**, **prose-gated opt-in** (no downstream drift). *Verify:* the
  checklist appears in the format/authoring guide and is referenced from the View-copy section.

### D. Wireframe & capability-index integration

- **FR-WCI-1 — Wireframe reports view-copy coverage (QUICK — catalog + Status model exist).** Add
  `"view_prose": "prisma/view_prose.yaml"` to `wireframe/inputs.py:30-38` CONVENTION_PATHS; a
  `_view_prose_state()` parallel to `_yaml_state()`; extend `_views_section()` (`plan.py:586-636`) to emit
  per-view chrome status using the existing `Status` model (`plan.py:45-50`). **Key by VIEW ident, not model
  (R1-S8)** — view_prose's keyspace is view names (same view-vs-model trap as FR-VCE-1), so the wireframe must
  match `_views_section`'s view idents, else FR-WCI-2's rollup denominator is wrong. *Verify:* `startd8
  wireframe` lists each view's copy status keyed by its view; a view with no `view_prose.yaml` entry reads
  `not_defined`/raw.
- **FR-WCI-2 — A unified "content/words completeness" rollup (MEDIUM — split from WCI-1).** Planning found
  the wireframe has per-surface status but **no aggregation**; a rollup needs a new `ContentCoverageStats`
  (pages + view copy + AI prompts) in `build_wireframe_plan()` + a `--json` `content_completeness` block
  (schema-version bump). *Verify:* the `--json` output carries the rollup; a separate, lower-urgency
  increment from WCI-1.
- **FR-WCI-3 — Capability-index entry for composite views + view copy.** Register
  `startd8.codegen.composite_views` (the view_codegen generator) and `startd8.codegen.view_prose` (the
  view-chrome capability) in `docs/capability-index/startd8.sdk.capabilities.yaml`, with evidence pointers
  and the multi-audience description. *Verify:* `/capability-index` validation passes with the two new
  entries.

### E. Functional quick wins (unblocked by the shipped fragment mechanism)

> **✅ Group E increment 1 DONE (2026-06-13, `feat/view-prose-group-e`).** FR-QW-1 fully + the
> `complete`-key slice of FR-QW-2 (the scope chosen at the talk-through). `empty` now renders on the
> detail-compose **pick-an-item index** (`{% if not roots %}`) and the **rendered-content list**
> (`{% if not rows %}`) in addition to model-compose, via a parameterized `_view_empty_block(guard=…)`
> + a widened `_has_empty_surface()` guard (computed-panel/export still loud-fail). New **`complete`**
> key → the computed-panel all-signals-met state (`render_view_complete_fragment` + `_view_complete_block`),
> its own untracked `_<view>.complete.html` fragment. All byte-identical-when-absent (8 new tests + 88
> view_codegen green). **Refinement vs the original cite:** the rendered-content has *two* surfaces — the
> **list** no-rows ("Nothing here yet.") is what `empty` overrides; the **detail** no-body ("Nothing to
> read yet.", a different semantic) stays literal and is **deferred** to a future `empty_body`-style key.
> **Deferred (chosen scope):** the index-prompt literal (FR-QW-2 tail) and all of FR-QW-3
> (validate-success is behavioral, not cosmetic; export per-control `help` slot exists but unwired).

- **FR-QW-1 — Extend `empty` to the other no-rows surfaces. ✅ DONE.** The untracked empty-fragment mechanism now
  exists; extend `empty` from model-compose to the `detail-compose` index "pick-an-item" page
  (`renderers.py:967`) and the `rendered-content` list empty (`:1026`), with the per-archetype guard. *Verify:*
  `empty` on those archetypes renders via a fragment and stays byte-identical when absent; on an archetype
  with no no-rows surface it still loud-fails.
- **FR-QW-2 — Route remaining hardcoded user-facing literals through prose (opt-in).** The
  `computed-panel` "All signals met." complete-state (`:1074`), the rendered-content "Nothing to read yet."
  (`:1021`), and the index prompt are authored copy baked in the renderers. Make each prose-overridable via
  an existing or minimal key, **defaulting to today's literal** (zero behavior change absent prose). *Verify:*
  each literal is overridable; absent prose ⇒ byte-identical.
- **FR-QW-3 — Finish the control follow-ups' tail.** Surface the deferred bits now that the mechanism is
  proven: a validate-success result line (today validate stays JSON) and per-control help on the export
  links — both prose-gated. *Verify:* authoring them renders; absent ⇒ byte-identical. *(Lower priority;
  may stay deferred.)*

### F. Design-principle elevation (architectural generalization)

- **FR-DP-1 — Name & document the prose-gated additive-manifest principle. ✅ DONE (2026-06-13).** Shipped
  as `docs/design-princples/SOTTO_DESIGN_PRINCIPLE.md` ("Sotto" そっと = *gently, without disturbing*;
  tagline "Don't disturb what exists"; diagnostic "when the content is absent, is the output byte-identical?").
  Covers the two generate-time fragment instances (pages, view-prose) + the ai-layer runtime variant, records
  the OQ-4 / FR-DP-2 drop rationale, and is indexed in CLAUDE.md's principle list. **Backlink closed
  (2026-06-13):** FR-FMT-3's "Words vs Structure" rule now links SOTTO from the format doc. Original spec:
  Add a cross-cutting principle
  doc (`docs/design-princples/`, beside MOTTAINAI/KAIZEN/WARM_UP/HAYAI) capturing the proven rule:
  *hash-exempt authored content lives in a standalone file rendered to an untracked (header-less) fragment;
  the owned template gains the include only when the content is present → byte-identical-when-absent → zero
  downstream drift.* Cover the **generate-time fragment** instances (pages + view-prose), and note the
  ai-layer prompt as a **related runtime-binding variant** (read at request time, not a generate-time
  fragment — planning, D8). *Verify:* the principle doc exists and is linked from the Words/Structure rule
  (FR-FMT-3).
- **~~FR-DP-2 — Extract a shared untracked-fragment primitive.~~ DROPPED (planning, D8).** The three
  mechanisms are **intentionally divergent** — pages/view-prose are generate-time fragments; the ai-layer
  prompt is **runtime-loaded** (`ai_layer.py:695-700`), not a fragment at all. Time-of-binding, format
  (markdown vs escaped vs raw), and discovery all differ, so a shared primitive isn't worth it (and is
  partly impossible). The pattern is **documented** by FR-DP-1 instead of extracted.

---

## 4. Open Questions (updated after planning)

- **OQ-1 — Carve group A out?** Group A (drift-recognition) is urgent, SDK-internal, and pre-dates
  view_prose. Recommend its own requirements doc + PR; this doc keeps the rest. *(Still open — decide at
  CRP/impl time.)*
- **OQ-2 — ✅ RESOLVED (planning).** No new plumbing: the backend `ProviderContext` already lets the
  provider resolve every manifest via conventional `prisma/` paths (the unused `_read_anchored` helper).
  FR-DRC-3 is a small thread-through.
- **OQ-3 — Kickoff manifest scaffolder.** Should the kickoff *emit* starter manifests for a new app? Note:
  Group G (FR-VCE-*) is the **derivation** path (reqs → manifests); a blank-scaffold path is a *different*,
  bigger capability. Deferred unless prioritized.
- **OQ-4 — ✅ RESOLVED (planning, D8).** FR-DP-2 dropped — the three mechanisms diverge (ai-layer is
  runtime-bound); document via FR-DP-1, don't extract.
- **OQ-5 — Wireframe rollup scope (FR-WCI-2).** Three-surface rollup (pages + view copy + AI prompts) the
  right denominator, or also form blurbs / entity titles? *(Keep v1 to the three; expand later.)*
- **OQ-6 (NEW) — Group G ingestion ordering.** FR-VCE-1 must run `parse_view_prose(known_views=…)` in the
  round-trip — which needs the **views** already extracted (to know the view names). Confirm the
  `extract.py` candidate ordering makes views available before view_prose. *(Verify-at-home; likely just
  ordering within `extract.py:145-158`.)*

---

## 5. Priority / sequencing (updated after planning)

1. **A (drift-recognition completeness)** — highest value; fixes silent $0→LLM fallthrough + 3 verified
   bugs; small thread-through (helpers already exist). Its own PR (OQ-1). *FR-DRC-1 first (unblocks 3+5).*
2. **G (view-copy extraction)** — highest *value* unlock; **FR-VCE-2 (close `Empty state:`) is the cheapest
   first slice** and proves the path; pairs with FR-FMT-1.
3. **D (FR-WCI-1 wireframe + FR-WCI-3 cap index)** — quick wins.
4. **C / B / F-doc** — cheap docs: FR-FMT-2/3/4 (no parser), FR-KIN-*, FR-DP-1.
5. **FR-WCI-2 (rollup)** + **FR-VCE-4 (display extraction parity)** — medium follow-ups.
6. **E (quick wins)** — opportunistic; lowest urgency.

---

*v0.4 — Phase-6 implementation reflection (Group A). Implementing against current main (`02920600`)
revealed the **editors-archetype merge had already shipped FR-DRC-2 + FR-DRC-3** (FR-ED-15/16) via a
"pass-all-manifests" design that **supersedes FR-DRC-1's `KIND_TO_INPUTS` map** (not built — would be
redundant). The one genuine remaining gap was the **view provider's missing `display.yaml` threading**
(FR-DRC-4) + a **provider-level recognition lock** (FR-DRC-5) — both shipped on
`feat/drift-recognition-group-a` (`65c82ad0`), the lock verified load-bearing (fails on pre-FR-DRC-4
code). Lesson: a CRP grounded at a fixed SHA can go stale if the codebase moves under it — re-verify
against current main at implementation time (which this Phase-6 step did, avoiding redundant re-work).*
*v0.3 — Post-CRP Round 1 (dual-document review, claude-opus-4-8[1m], code-grounded @ `0e8d08fb`). 10
F-suggestions applied (Appendix A), 0 rejected; all high-severity findings independently verified. Key
corrections: **`KIND_TO_INPUTS` can't span all 5 providers** — only backend has kinds; rescoped to
backend-map + per-provider `declared_inputs` (F1/F3); FR-DRC-5 enumerates per-provider, non-vacuously (F2);
**`known_views` ≠ the graph** (it yields model names, no `all_view_names()`) so FR-VCE-1 must harvest view
idents from the views candidate (F5); **FR-VCE-2 needs an archetype filter** or it loud-fails existing reqs
docs that carry `Empty state:` on a board/dashboard (F6); **FR-DRC-3 is a cost-behavior change** needing a
flag/changelog gate for the ~9 downstream repos (F4); FR-VCE-4 gated on a display.yaml field-derivability
table (F7); + escaping contract (F9), shared-lock carve-out note (F10). Group A reaffirmed as its own PR.*
*v0.2 — Post-planning self-reflective update (reflective loop Phase 4). Plan
`VIEW_PROSE_FOLLOWTHROUGH_PLAN_v0.1.md` (grounded at `0e8d08fb`) drove: **FR-FMT-1 promoted to a new Group
G** (the reqs doc is a deterministic $0 manifest compiler that doesn't yet emit `view_prose.yaml`); a **new
quick win FR-VCE-2** (the already-authored `Empty state:` dead-end the view_prose machinery can now light
up); a **manifest-extraction-parity** theme (FR-VCE-4 / display.yaml — the derivation emits 6/8). Group A
confirmed a small thread-through (helpers exist, unused); FR-DRC-2 reframed as `_FLOWS_KINDS`; FR-DRC-5
widened to all 5 providers. FR-FMT-2 narrowed to pure doc; **FR-DP-2 dropped**; **FR-WCI split** (1 quick, 2
medium). OQ-2/OQ-4 resolved; OQ-6 added.*
*v0.1 — Initial draft (Phase 1), grounded in SDK `main` @ `0e8d08fb` + strtd8 kickoff/assembly docs.*

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
| R1-F1 | `KIND_TO_INPUTS` can't span 5 providers — rescope | R1 (code-verified) | **Applied.** FR-DRC-1 rescoped: backend kind-map + per-provider `declared_inputs` for the 4 kindless providers. | 2026-06-12 |
| R1-F2 | FR-DRC-5 enumeration source per provider (non-vacuous) | R1 | **Applied.** FR-DRC-5 enumerates each provider's own recognition surface + asserts non-empty. | 2026-06-12 |
| R1-F3 | FR-DRC-1 fail-closed on unknown backend kind | R1 | **Applied.** Fail-closed clause added (preserve `tampered` posture). | 2026-06-12 |
| R1-F4 | FR-DRC-3 cost-behavior change → flag/changelog gate | R1 (code-verified) | **Applied.** Behavior-change gate + AC added; ~9 downstream repos noted. | 2026-06-12 |
| R1-F5 | `known_views` ≠ `graph.all_model_names()` (no `all_view_names`) | R1 (code-verified @0e8d08fb) | **Applied.** FR-VCE-1 sources view idents from the views candidate / adds `all_view_names()`. | 2026-06-12 |
| R1-F6 | FR-VCE-2 archetype filter before routing `Empty state:` | R1 (code-verified) | **Applied.** Route only model-compose; silent-drop off-archetype (back-compat). | 2026-06-12 |
| R1-F7 | FR-VCE-4 display.yaml authoring-feasibility gate | R1 | **Applied.** Field-derivability table prerequisite; splits if any field needs new authoring. | 2026-06-12 |
| R1-F8 | Mark load-bearing anchors verified-at `0e8d08fb` | R1 | **Applied (light).** The R1-verified anchors (provider.py:62-101, extract.py:161, renderers.py:~1853) carry "code-verified" inline. | 2026-06-12 |
| R1-F9 | FR-VCE-1 escaping/injection contract | R1 | **Applied.** Extractor must honor the renderer's per-archetype escaping. | 2026-06-12 |
| R1-F10 | FR-DRC-5 lock is a shared artifact across the OQ-1 carve-out | R1 | **Applied.** Carve-out note: shared `tests/unit/` path. | 2026-06-12 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — all R1 F-suggestions accepted; the high-severity findings were independently code-verified at `0e8d08fb`) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-06-12 UTC

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-06-12 19:05:00 UTC
- **Scope**: Requirements review (F-prefix) with code-grounded verification of Group A drift registries (`backend_codegen/drift.py`, `provider.py`), all 5 deterministic providers' recognition mechanisms, `manifest_extraction/extract.py`+`extractors.py`, and `view_codegen/renderers.py` archetype loud-fail. Sponsor focus asks answered first.

##### Sponsor focus-asks (answered at top, per prompt template)

**Ask 1 — Is one declarative `KIND_TO_INPUTS` map (FR-DRC-1) achievable across 5 providers, and can FR-DRC-5 enumerate every owned kind?**
- **Summary answer:** Partial — a `KIND_TO_INPUTS` map is achievable **only for the backend provider** (the one provider with discrete embedded "kinds"); the other 4 providers have **no kinds at all**, so a single map cannot be their source of truth.
- **Rationale:** Code-verified: backend routes on `embedded_artifact_kind()` via `_AI_KINDS`/`_PAGES_KINDS`/`_FORMS_KINDS`/`_SETTINGS_KINDS` + `_renderers()` keys (`drift.py:47-74,560-575`). But frontend's `owned_file_in_sync` is **schema-only with no kind** (`frontend_codegen/provider.py:25-36`); scaffold recognizes via `is_owned_scaffold_file()` marker + `app.yaml`, no kind (`scaffold_codegen/provider.py:23-29`); polish recognizes via `POLISH_MARKER` + **path-suffix dispatch** in `_render_for()` (`presentation_polish/provider.py:54-90`), no enumerable kind list; view recognizes via `is_owned_view_file()` marker + whole-set render, no kind (`view_codegen/provider.py:20-37`). FR-DRC-5 claims it will "enumerate every owned kind across … view, scaffold, frontend, and polish providers" — but those providers expose **no kind enumeration surface** to enumerate.
- **Assumptions / conditions:** Holds unless FR-DRC-1/5 are rescoped to "input-set per *provider/recognition-unit*" rather than "per *kind*".
- **Suggested improvements:** see R1-F1 (rescope the map abstraction) and R1-F2 (FR-DRC-5 enumeration source). The failure mode "a provider owns a kind absent from the map" is real for backend (covered by R1-F3 fail-closed), but for the 4 kindless providers the more dangerous failure is **silent under-coverage** — the lock passes vacuously because there is nothing to enumerate.

**Ask 2 — Does FR-DRC-3 wiring change behavior for EXISTING apps (false-$0-skip files flipping to LLM)? Stage/flag it?**
- **Summary answer:** Yes — it is a genuine behavior change for in-flight apps and should be staged/flagged, not shipped silently.
- **Rationale:** Today `is_in_sync` → `owned_file_in_sync(schema_text, content)` passes **schema only** (`provider.py:29-35`, `drift.py:325-339`); a `fastapi-web-forms`/`htmx-created` file whose `views.yaml forms:` changed but schema didn't will currently report `in_sync` (false $0-skip) because `_check_forms_drift` never sees `forms_text`. After FR-DRC-3 it correctly flips to not-in-sync → LLM. That is a **correctness fix**, but it silently moves cost for downstream apps mid-build.
- **Assumptions / conditions:** Only affects apps with non-trivial `forms:`/AI/pages manifests already on disk.
- **Suggested improvements:** see R1-F4 — add an acceptance criterion + a one-line migration/changelog note ("FR-DRC-3 may re-classify previously-skipped manifest-derived files; expect a one-time $-delta").

**Ask 3 — OQ-6 ordering + FR-VCE-2 `Empty state:` back-compat.**
- **Summary answer:** Both concerns are real and under-specified. OQ-6's stated mitigation ("ordering within `extract.py:145-158`") is **insufficient**; FR-VCE-2 has a live loud-fail back-compat hazard.
- **Rationale:** Code-verified: the round-trip's `known` is `graph.all_model_names()` (`extract.py:161`) — **model names, not view names**. `parse_view_prose(known_views=…)` (`view_prose.py:59-79`) expects **view** names, and the graph exposes only `all_model_names()` (`entities.py:121`); there is **no `all_view_names()`**. So FR-VCE-1 cannot get `known_views` from the graph regardless of candidate ordering — it must harvest extracted view idents from the `views.yaml` candidate dict, a cross-candidate data dependency the doc doesn't name. Separately, the renderer raises `ValueError` for `empty` on any non-model-compose view at **render time** (`renderers.py:1859-1864`); routing a board/dashboard `Empty state:` into `view_prose.yaml` `empty:` would make a today-silently-dropped field start loud-failing existing reqs docs at ingestion.
- **Assumptions / conditions:** none.
- **Suggested improvements:** see R1-F5 (OQ-6: name the view-name source, not just ordering) and R1-F6 (FR-VCE-2 archetype filter before routing).

**Ask 4 — FR-VCE-4 display.yaml feasibility / scope.**
- **Summary answer:** Depends — view_prose is words-only (flat per-view strings) and tractable; `display.yaml` carries structure/bindings (column order, FK label resolution) that the reqs doc may not author, so it is a materially bigger lift and should not ride FR-VCE-1's coattails.
- **Rationale:** FR-VCE-4 already self-flags "lower urgency"; the risk is that "8/8 parity" framing implies symmetric effort. The doc gives no evidence the `### View:` block authors column order / FK display fields.
- **Assumptions / conditions:** none.
- **Suggested improvements:** see R1-F7 — add an explicit authoring-gap acceptance gate (what display.yaml fields are derivable vs require new authoring) before committing FR-VCE-4 to the same group.

**Ask 5 — Carve Group A into its own doc/PR (OQ-1)?**
- **Summary answer:** Yes — recommend carving Group A out; it has a different risk profile (pre-existing correctness fix with a cost-behavior change, ask 2) from the additive Group G/D/C work. (S-side detail in plan R1-S1.)

##### Numbered suggestions (F-prefix)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | FR-DRC-1: rename/rescope the abstraction from per-**kind** `KIND_TO_INPUTS` to a per-**recognition-unit** input declaration. State explicitly that the map is backend-only (kinds) and that frontend/scaffold/polish/view declare their input-set at the **provider** level (schema-only; app.yaml; theme-manifest; schema+views+view_prose+display). | Code shows only backend has discrete kinds (`drift.py:47-74`); the other 4 use markers/path-suffix (`frontend/scaffold/polish/view provider.py`). A literal "kind→inputs" map cannot be the SSOT for kindless providers. | FR-DRC-1 text | Unit test: each provider exposes a declared input-set; assert the CLI and skip-hook both read it. |
| R1-F2 | Validation | high | FR-DRC-5: specify the **enumeration source per provider** — backend = `_*_KINDS` ∪ `_renderers()` keys; the 4 kindless providers = their `owns()`-recognized artifact set (e.g. polish's `_CONSTANT_PARTIALS` + stylesheet/static-setup relpaths, view's owned-file set). Without this, the lock passes **vacuously** for providers it can't enumerate. | FR-DRC-5 says it enumerates "every owned kind … view, scaffold, frontend, polish" but those have no kind list (verified). A test that enumerates nothing gives false assurance. | FR-DRC-5 *Verify:* clause | The lock test must assert a **non-empty** enumerated set per provider and fail if a provider contributes zero. |
| R1-F3 | Risks | medium | FR-DRC-1: add the explicit failure-mode requirement — "if a backend owned kind is absent from `KIND_TO_INPUTS`, drift verification must **fail closed** (treat as not-in-sync), never silently schema-only-verify." | `check_drift` currently falls through to schema-only `_renderers()` lookup for unknown kinds and returns `tampered` (`drift.py:600-606`) — good, but FR-DRC-1's new map must preserve that fail-closed posture, not introduce a permissive default. | FR-DRC-1 text | Test: a synthetic kind not in the map → skip-hook returns not-in-sync. |
| R1-F4 | Ops | high | FR-DRC-3: add an acceptance criterion + changelog/migration note that wiring the manifests will **re-classify previously-skipped manifest-derived files** in existing apps (one-time $-delta), and decide whether it ships behind a flag for one release. | Verified: today's schema-only `owned_file_in_sync` false-$0-skips forms/AI/pages files whose manifest changed; FR-DRC-3 correctly flips them to LLM (sponsor ask 2). Silent cost shifts surprise downstream consumers (per MEMORY: 9 downstream repos track the live branch). | FR-DRC-3 *Verify:* clause + a new note in §2 Non-goals or §5 | Add an AC: "a pre-FR-DRC-3 in-sync forms file with a changed `forms:` reports not-in-sync after the change; documented as expected." |
| R1-F5 | Data | high | OQ-6 / FR-VCE-1: replace "likely just ordering within `extract.py:145-158`" with the real dependency — `known_views` is **not** `graph.all_model_names()` (that's models); there is no `all_view_names()` on the graph. Specify that FR-VCE-1 must source view idents from the **extracted `views.yaml` candidate** (or add `all_view_names()`). | Verified: `extract.py:161` uses `graph.all_model_names()`; `parse_view_prose` wants view names (`view_prose.py:59-79`); `entities.py:121` has only `all_model_names()`. Ordering alone won't supply view names. | OQ-6 text + FR-VCE-1 | Test: a reqs doc whose view-copy references a view name absent from the views section fails ingestion; one referencing a real view passes. |
| R1-F6 | Risks | high | FR-VCE-2: require the extractor to route `Empty state:` to `view_prose.yaml` `empty:` **only for model-scoped detail-compose views**, and to keep dropping it (no error) on other archetypes — preserving today's silent-drop for back-compat. | Verified: the renderer raises `ValueError` for `empty` on non-model-compose at render time (`renderers.py:1859-1864`). Routing every `Empty state:` blindly would make existing reqs docs (board/dashboard with `Empty state:`) start loud-failing. | FR-VCE-2 + FR-VCE-3 | Test: a board view with `Empty state:` extracts with **no** `empty:` entry and **no** error; a detail-compose view with `Empty state:` produces `empty:`. |
| R1-F7 | Interfaces | medium | FR-VCE-4: add an authoring-feasibility acceptance gate enumerating which `display.yaml` fields are derivable from the `### View:` grammar (and which — column order, FK label resolution — are not) **before** committing it to Group G; otherwise mark it explicitly out-of-scope for this doc's PR. | Sponsor ask 4: display.yaml carries structure/bindings the reqs doc may not author. "8/8 parity" framing hides asymmetric effort vs flat view_prose strings. | FR-VCE-4 text | Manual: produce the field-derivability table; if >0 fields need new authoring, FR-VCE-4 moves to its own increment/OQ. |
| R1-F8 | Validation | low | §0.5 / FR citations: the doc labels SDK file:line claims "verify-at-home" but several are load-bearing (FR-DRC-3, FR-VCE-1, FR-VCE-2). Add a one-line "verified-at `0e8d08fb`" marker on the **load-bearing** anchors that have been re-checked, distinguishing them from the soft ones. | Reduces the chance a future reviewer re-verifies already-confirmed anchors; this round confirmed `provider.py:62-101`, `extract.py:161`, `renderers.py:1859`. | §0.5 / FR anchor lines | A reviewer cross-checks the marked anchors once; marker stays until a refactor moves the line. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Security | low | FR-VCE-1: require the extractor to **size-bound / sanitize** authored view-copy before it lands in an untracked rendered fragment (the copy is author-controlled text that becomes page HTML). State the escaping contract (the renderer's existing markdown-vs-escaped-vs-raw handling) the extractor must honor. | View copy flows author text → fragment → served page; FR-DP-1 already notes format divergence (markdown/escaped/raw). An extractor that emits raw into a raw-include archetype is an injection surface. | FR-VCE-1 / FR-VCE-3 | Test: a view-copy value containing HTML/`{{ }}` renders escaped per the target archetype's contract. |
| R1-F10 | Architecture | medium | OQ-1 / FR-DRC-5: if Group A is carved into its own PR (recommended), the cross-provider regression lock (FR-DRC-5) still touches **all 5 providers** including those owned by Group-G-adjacent code (view/polish). Note the lock test is a **shared** artifact that must move with Group A but assert against providers Group A doesn't otherwise modify. | The lock spans providers beyond backend; a clean Group-A carve-out must not orphan or duplicate it. Cross-cutting concern not addressed by OQ-1's framing. | OQ-1 text | The lock test lives in a shared `tests/unit/` path imported by both PRs; CI runs it on both. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; Appendix A/B/C carry no prior items.
