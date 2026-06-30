# View `Shows:` Panels Grammar — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-29
**Status:** IMPLEMENTED 2026-06-29 (per Plan v1.0 — matched the plan with no implementation surprises;
the reflective pass had already removed the surprises)
**Parent:** [`KICKOFF_AUTHORING_CONTRACT.md`](KICKOFF_AUTHORING_CONTRACT.md) §2.3 (grammar v0.3 → v0.4)
**Closes:** lane D9 / spike-finding F3 (`../wireframe/spike-2026-06-05/SPIKE_FINDINGS.md`) / REQ-VIEW
**Consumer:** `manifest_extraction.extract_views` → `views.yaml` → `view_codegen.parse_views`

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the `view_codegen` schema/renderer and the round-trip gate, and revealed
> the implementation is **substantially smaller and narrower** than the spike's "relations/panels
> enrichment" framing implied. Four corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Closing D9 needs a `view_codegen` "relations/panels enrichment" (schema/renderer work) | `Panel{name,fields,show_when}` **already parses generically** in `parse_views` and **already renders** in `_render_detail_compose` (`panels[name] = any(root.<f> set …)`). The schema + renderer half is done. | **No `view_codegen` changes.** D9 = contract §2.3 grammar + `extract_views` production + tests only. Scope drops from "medium-large" to "small-medium". |
| Grammar covers detail-compose **and workspace** (per spike F3 wording) | `_render_workspace` is **polymorphic-only** — it never consumes `panels`. Only detail-compose renders panels. | **Detail-compose only** (FR-2). Workspace `Shows:` prose correctly stays flagged (non-req confirmed). |
| Need both a relations and a panels production | Relations are **already fully covered** by the arrow grammar (`A→B`). | The only missing surface is **panels**. The feature is "panels", not "relations/panels". |
| Field validation can lean on `parse_views`' field gate | The views round-trip gate calls `parse_views(t, known_entities=known)` — it does **not** pass `known_fields`, so the field check is a no-op for panels. | **FR-3 is load-bearing, not defensive**: the extractor self-validating fields against the §2.1 graph is the *only* guard against a bad field reaching `generate views`. |

**Resolved open questions:**
- **OQ-1 → `- Panel: <Name> = <f>, <f>, …`.** A distinct key, not an overload of the arrow `Shows:`
  (keeps the two productions unambiguous; repeatable per FR-5).
- **OQ-2 → workspace is out.** The workspace renderer is polymorphic-only; panels are detail-compose-only.
- **OQ-3 → extractor self-validates.** The gate doesn't pass `known_fields`; the producer resolves each
  field against the Root entity's §2.1 fields and emits only resolved ones (FR-3/FR-8).
- **OQ-4 → tolerate a trailing parenthetical per field token** (mirrors the arrow grammar's annotation
  tolerance): `Panel: Details = title, story (the STAR narrative)` → fields `[title, story]`.
- **OQ-5 → panel name is free text, annotation-stripped.** It is a string dict key (repr'd in generated
  code) — no identifier constraint needed.

---

## 1. Problem Statement

§2.3's `Shows:` line has exactly two deterministic productions today:
- **arrow** (`A→B`) → `relations` entries (resolved via §2.1 join models), and
- **counts** (`counts of X per Y`) → `aggregates`.

A third, common authoring intent — *"surface these specific root fields as a grouped panel"* —
has **no grammar**. Such lines fall into the "neither arrow nor counts" bucket and are flagged
`not_extracted(prose)`; the view round-trips and renders as a **shell** (empty `panels`). This is
*correct* per flag-don't-guess, but it leaves a whole authoring intent unexpressible: the
`view_codegen` schema already has a `Panel{name, fields, show_when}` type and a renderer that emits
conditional panels (`panels[name] = any(root.<field> is set …)`), yet **the extractor never emits a
panel** — there is no authoring surface for it.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Contract §2.3 `Shows:` grammar | arrow + counts productions | no "surface root fields as a panel" production |
| `extract_views` (`extractors.py` ~L223) | arrow→relations, counts→aggregates, else→`not_extracted(prose)` | never emits `panels`; field-list intent is lost to the prose bucket |
| `view_codegen` `Panel{name,fields,show_when}` | fully implemented + rendered (`any_set`) | unreachable from authored prose — schema with no front door |
| Genuinely-unstructured prose (`everything about one profile in prose form`) | `not_extracted(prose)` | **must stay flagged** — this is correct, not a gap |

## 2. Requirements

- **FR-1 — A constrained Panel line in §2.3.** Add the production `- Panel: <Name> = <field>, <field>, …`
  (decided, OQ-1) — a key-line in the `### View:` block, distinct from the arrow `Shows:`. It maps to a
  `Panel{name=<Name>, fields=[…], show_when=any_set}` entry on the view's `panels`. The name is free
  text (annotation-stripped); each field token tolerates a trailing parenthetical (OQ-4).
- **FR-2 — Detail-compose scoped.** The Panel production is valid on `detail-compose` (row- and
  model-scoped). On other kinds it is **off-archetype** and flagged (not silently accepted), mirroring
  how `Group by:`/`compute`/`content_field` are kind-gated.
- **FR-3 — Fields resolve against the Root entity, flag-don't-guess.** Each field token is resolved
  (case-tolerant) against the Root entity's declared §2.1 fields. An unknown field → the panel entry
  is `not_extracted` (named, advisory) and dropped — never a guessed field name (a wrong field passes
  the YAML round-trip and fails only at `generate views`).
- **FR-4 — `show_when` defaults to `any_set`.** v1 emits `show_when: any_set` (the only value the
  renderer supports). The grammar reserves room for future values but does not invent them.
- **FR-5 — Repeatable.** A view may declare multiple `Panel:` lines; each is an independent entry.
- **FR-6 — Genuinely-unstructured prose still flagged.** A `Shows:`/`Also shows:` line that matches
  neither arrow, counts, nor the new Panel production stays `not_extracted(prose)`. The new production
  does not weaken flag-don't-guess.
- **FR-7 — Byte-identical-when-absent.** A view with no Panel line emits no `panels` key; `views.yaml`
  and all downstream output are byte-identical to today.
- **FR-8 — Round-trips through `parse_views`.** The emitted `panels` block parses cleanly (the
  extractor only emits resolved fields, so the round-trip never trips `parse_views`' field gate).
- **FR-9 — Two report rows where appropriate.** Each Panel line yields an `extracted` record for the
  panel; an unresolved field within it yields its own `not_extracted` record (traceability — the
  author's field token is never silently dropped).

## 3. Non-Requirements

- **No new relation grammar.** Relations are already fully covered by the arrow production; this work
  adds **panels only**.
- **No workspace Shows extraction.** A `workspace` view resolves its content polymorphically (the
  whole record); its `Shows:` prose is descriptive and stays flagged — no panel/relation grammar for
  workspace. (Spike F3 lumped "detail-compose/workspace"; planning will confirm workspace is out.)
- **No new `show_when` modes.** v1 = `any_set` only (the only rendered mode).
- **No prose→panel inference.** We do not parse free prose into fields; only the constrained
  `Panel: Name = a, b, c` form extracts.
- **No `Panel:` on dashboards/boards/export-package/computed-panel/rendered-content/import-flow.**

## 4. Open Questions

All five v0.1 open questions were resolved by the planning pass — see §0. None remain.

---

*v0.2 — Post-planning self-reflective update. 1 requirement narrowed (FR-2 detail-compose only),
0 added, 0 deferred, 5 open questions resolved. Key discovery: no `view_codegen` changes needed —
the Panel schema/renderer already exist, so D9 is a contract + extractor change.*
