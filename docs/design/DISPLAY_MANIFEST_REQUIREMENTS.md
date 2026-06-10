# Presentation/display layer — `display.yaml` (structure) — Requirements

**Version:** 0.2 (post-investigation)
**Date:** 2026-06-10
**Status:** Increment 1 IMPLEMENTED 2026-06-10 — FR-DM-1..5 (`display_manifest` parser + entity list
columns/labels/order/label_field/format + detail sections + `--display` wiring + drift consistency,
which also closed the latent P0-2 filter-template drift gap). Runtime-proven. 375 passed.
**Increment 2 IMPLEMENTED 2026-06-10** — FR-DM-6 (composite-view FK resolution): a model-compose view's
relations resolve `via_fk → target entity → label_field` (kills `neil-cpo-01`); `root_label_field` sets
the group heading; `generate views --display` + drift consistency. Opt-in; unresolvable FK falls back.
**Increment 3 (FR-DM-7) IMPLEMENTED 2026-06-10 — Part A (always-on zero-config defaults):** list/detail
now drop id + provenance/timestamps by default (reusing the forms omit policy) and the row link reads as
the heuristic label (name/title/label/headline) — a zero-config app no longer leaks ids. **Part B
(wireframe `display` coverage section) deferred** — a Low-severity advisory addition (an 8th catalog key
that ripples the wireframe determinism/cross-check goldens); not worth the churn vs the zero-config value.
**Scope:** strtd8 `SDK_PRESENTATION_DISPLAY_HANDOFF_2026-06-10` — a new **`display.yaml`** manifest giving
the generators the display metadata they lack, so generated screens stop leaking system IDs as labels
(`neil-tr-01`). The **structure** sibling of #7 (view prose = words); they meet on composite views,
zero key overlap. **$0, deterministic, 0 LLM.**
**Component:** `backend_codegen` (new `display_manifest.py`; entity list/row/detail), `view_codegen`
(composite-view FK resolution), `cli_generate` / `assembler` (wiring).

## 0. Planning insights / OQ resolutions

| OQ / assumption | Resolution |
|------------------|-----------|
| **OQ-A drift-hash partition** | Accept partition. The display-derived templates hash the **binding structure** (entity/columns-order/sections/label_field/format) — inline copy strings (`title`/`subtitle`/column `label`) are **hash-exempt** so copy edits don't trip `--check`. Matches the FR-PG-7 prose-outside-hash precedent. |
| **OQ-B always-on defaults** | **Deferred to increment 3.** Applying the label heuristic + system-field hide to *every* app with no manifest is a global behavior change with large golden-test churn. v1 is **manifest-opt-in per entity** (zero-config apps unchanged, byte-identical). Always-on is a clean follow-on once the manifest path is proven. |
| **OQ-C relation depth** | One hop (join → entity → `label_field`) in v1; two-hop declarable later. |
| **OQ-D format vocab** | Closed v1 set: `badge`, `truncate:N`, `date`, `link`. Unknown → loud. |
| **OQ-E reserved keys** | `searchable`/`paginate`/`filters` etc. → **reject loud** until built. |
| **OQ-F theme** | App-owned `app/static/css/app.css` for the baseline; `presentation_polish` vendoring later. Out of this manifest. |
| **OQ-G frontend-design path** | Non-functional (SkillAgent can't run a user-skill); Tier-2 bespoke deferred. Not blocking. |
| `display.yaml` shares views.yaml | It's its **own** manifest (`prisma/display.yaml`) with a `--display` flag, mirroring `--pages`/`--views` (the team's spec). |
| It's one big change | The 3 visible surfaces are independent → **3 increments**: (1) parser + entity list/detail display + wiring; (2) composite-view FK resolution (kills `neil-cpo-01`); (3) always-on defaults + wireframe `display` section + #7 coordination. |

## 1. Functional Requirements

> Increment tags: **[I1]** parser+entity display (this pass), **[I2]** view FK resolution, **[I3]** defaults+wireframe.

- **FR-DM-1 [I1] — `display.yaml` parser.** `parse_display(text, schema)` → `{entity: EntityDisplay}`
  (+ `{view: ViewDisplay}`), frozen dataclasses, strict: unknown keys / unknown entity / unknown field
  refs / unknown `format` fail loud against the contract. Shapes (the handoff §2.1): `ColumnDisplay
  (field,label,format)`, `DetailSection(title,fields)`, `EntityDisplay(entity,title,subtitle,
  label_field,columns,sections,hidden_fields,default_sort)`, `RelationDisplay(name,via_fk,label_field)`,
  `ViewDisplay(view,root_label_field,relations)`. Verify: a valid doc parses; each bad-ref class raises.

- **FR-DM-2 [I1] — Entity list columns/labels/order + label_field.** When an entity has an
  `EntityDisplay`, the list `<thead>` + row `<td>`s use `columns` (in declared order, with `label`
  headers and `format`); `hidden_fields` are omitted; the row's view/edit link text uses `label_field`
  (not `id`). Verify: a configured entity's list shows the declared columns/labels in order, hides the
  hidden ones, and links by the label field; an unconfigured entity is byte-identical.

- **FR-DM-3 [I1] — Detail sections.** With `sections`, the detail page renders grouped
  `<section><h2>{title}</h2>` blocks over the listed fields instead of the flat `<dl>` dump; `title`/
  `subtitle` head the page. Verify: a configured detail page groups fields by section; unconfigured is
  byte-identical.

- **FR-DM-4 [I1] — Wiring.** `render_backend` gains optional `display_text`; `generate backend` (and
  `views`) gain `--display prisma/display.yaml`, mirroring `--pages`/`--views`. Verify: the flag threads
  the manifest; absent ⇒ unchanged output.

- **FR-DM-5 [I1] — `format` rendering.** `badge` wraps the value in a `<span class="badge">`;
  `truncate:N` truncates with Jinja `|truncate(N)`; `date` formats a datetime; `link` makes the value a
  link to the row. Verify: each format renders its wrapper/transform.

- **FR-DM-6 [I2] — Composite-view FK resolution.** The view data-fetch resolves `RelationDisplay.via_fk
  → target entity → label_field`, handing the template `{id, label}` per relation row instead of the
  join row (the fix that kills `neil-cpo-01`); `root_label_field` sets the group heading value. *(I2 —
  not this pass.)*

- **FR-DM-7 [I3] — Zero-config defaults + wireframe.** Label heuristic (`name`/`title`/`label`/
  `headline` over `id`) + system-field hide even without a manifest; a wireframe `display` coverage
  section. *(I3 — not this pass.)*

## 2. Non-Requirements

- **No user copy in `display.yaml`** — `ViewDisplay` carries bindings only; view words live in #7
  (`views.yaml prose:`). One screen, two manifests, zero key overlap.
- **Reuse `_PROVENANCE_OMIT`** for list/detail field-hide (the same set forms already omit) — one
  omission policy, don't fork it.
- **No LLM / no client JS.**

## 3. Acceptance (increment 1)

1. `parse_display` strict-parses valid docs; each bad-ref class fails loud.
2. A configured entity's list (columns/labels/order/hidden/label_field/format) and detail (sections/
   title) render per the manifest; unconfigured entities are byte-identical (manifest-opt-in).
3. `--display` threads the manifest; absent ⇒ unchanged. Runtime-proven (TestClient renders a
   configured list + detail).
