# <Project> — Composite Views (prose source)                                 [TEMPLATE]

> **TEMPLATE** — copy to `<project>/docs/kickoff/authoring/views.md`, replace every `<…>`, delete
> the `▷` guidance lines and this banner, then author one `### View:` block per screen. Validate
> with `startd8 kickoff check docs/kickoff/authoring/views.md` (writes nothing), iterate until it
> reports the views as `extracted`, then let the extractor emit `prisma/views.yaml`.

**Version:** 0.1
**Date:** <YYYY-MM-DD>
**What this is:** the **prose-authored source** for `prisma/views.yaml`, written to the Kickoff
Authoring Contract **§2.3 Views** grammar. It is human-readable *and* deterministically
extractable — unlike the value-input prose sources (conventions/build-prefs/…), **views already
has a working extractor**, so this round-trips today. Prose outside the `## Views` section is
tolerated and ignored (contract §1: *the format carries the truth*).

> **Prerequisite (sequencing — contract §2.3):** the Views extractor runs **after** the
> entity/relationship pass, so `Root`, `Shows:` and aggregate `fk` values resolve against your
> `prisma/schema.prisma`. Author the contract first; a `Shows:`/aggregate that names an unknown
> entity or relation is flagged `not_extracted`, never guessed.

---

## Views

▷ One `### View: <Name>` block per composite screen. The view NAME comes from the heading (a
▷ trailing `*(…)*` annotation is stripped); the ROUTE is DERIVED from the kind — never author URLs
▷ unless overriding (see the reference below). Pick the Kind from the published five.

### View: <Catalog Dashboard>

▷ dashboard = counts & summaries over one root entity. Requires Kind + Root. Add aggregates as
▷ "counts of <Child> per <Root>" → `aggregates{name, of, fk}` (fk resolves from the join/child FK).

- Kind: dashboard
- Root: <RootEntity>
- Shows: counts of <ChildEntity> per <RootEntity>
- Title: "<the human page heading>"
- Intro: "<one sentence under the title, in user language>"

### View: <Record Workspace>

▷ workspace = everything about ONE record (route is parameterized: /<root>/{id}). Kind + Root only.

- Kind: workspace
- Root: <RootEntity>
- Title: "<Workspace heading>"

### View: <Connected Picture> *(detail-compose)*

▷ detail-compose = one connected picture from several record types. `Scope: model` makes it a
▷ whole-model map (every root + relations on ONE page) and is what gives it an Empty state.

- Kind: detail-compose
- Root: <RootEntity>
- Shows: <RootEntity>→<EntityA>, <RootEntity>→<EntityB>   *(only user-linked rows)*
- Scope: model
- Empty state: "<what shows when there are no rows>"

### View: <Status Board>

▷ board = status columns. REQUIRES `Group by:` (a field on the Root entity — the column
▷ discriminator) AND `Order:` (the allowed column values, in order — a static board's columns).
▷ Omitting `Order:` is a hard error (`board '<name>' requires an Order:`); for runtime-derived
▷ columns use an entity-backed board (`Columns from:`) instead. If a column value contains a
▷ literal pipe, escape it as `\|`.

- Kind: board
- Root: <RootEntity>
- Group by: <statusField>
- Order: <value-1>, <value-2>, <value-3>

### View: <Workspace Export> *(export-package)*

▷ export-package = a downloadable bundle of a workspace. REQUIRES `Of:` (the workspace view it
▷ bundles) + `Formats:`. No Root (it carries the workspace's).

- Kind: export-package
- Of: <Record Workspace>
- Formats: json, md

---

## Per-archetype reference (cheat-sheet — prose, ignored by extraction)

| Kind | Required keys | Optional | Route (derived) |
|------|---------------|----------|-----------------|
| `dashboard` | Kind, Root | Shows / aggregates ("counts of X per Y") | `/<kebab(name)>` |
| `board` | Kind, Root, **Group by**, **Order** (static) *or* **Columns from** (entity-backed) | — | `/<kebab(name)>` |
| `workspace` | Kind, Root | — | `/<kebab(root)>/{id}` |
| `detail-compose` | Kind, Root | Shows, **Scope: model**, Empty state | `/<kebab(name)>` |
| `export-package` | Kind, **Of**, **Formats** | — | `<of-view-route>/export.{fmt}` |
| `computed-panel` | Kind, **Compute** *(no Root)* | — | `/<kebab(name)>` |

**View COPY → `view_prose.yaml` (the hash-exempt WORDS layer, contract §2.3):** `Title:` / `Intro:`
work on any view; `Empty state:` only on `Scope: model` detail-compose; `Success:` / `Error:` /
`Controls:` only on `import-flow`. Off-archetype copy keys are ignored without error. Editing copy
never trips `generate … --check` (SOTTO).

**Route override (optional):** add `- Route: /custom` to a block to override the derivation —
permitted for views (workspace/export routes are parameterized). Authored data, never an LLM product.

**Flag-don't-guess (contract §3):** any non-conforming line → `not_extracted(<reason>)` in the
`kickoff check` report — never silently dropped, never guessed.

---

## Extraction expectation (what §2.3 should produce)

▷ Update this block to mirror your filled views above — it is the round-trip acceptance target
▷ (the team confirms the extractor emits exactly this `prisma/views.yaml`).

```yaml
views:
  - {name: <Catalog Dashboard kebab>, kind: dashboard, root: <RootEntity>, route: /<…>,
     aggregates: [{name: <child>_count, of: <ChildEntity>, fk: <rootEntity>Id}]}
  - {name: <Record Workspace kebab>, kind: workspace, root: <RootEntity>, route: /<root>/{id}}
  # …one entry per `### View:` block above
```

*Authored to Kickoff Authoring Contract §2.3. Companion value-input prose sources
(`conventions.md`, …) follow the FR-VIP pattern but await their extractors; views extracts today.*
