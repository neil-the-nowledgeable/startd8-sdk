# FR-VCE-4 — `display.yaml` Field-Derivability Table (the gate artifact)

**Status:** Feasibility gate — **CLOSED with a SPLIT** (2026-06-13)
**Decides:** whether manifest-extraction can emit `display.yaml` from the reqs `### Entity` / `### View:`
grammar (parity with FR-VCE-1's `view_prose.yaml`), and for which fields.
**Verdict:** the derivable subset is **empty of value-carrying fields** → extraction emits **no
`display.yaml`**; FR-VCE-4 **splits to its own increment** (new **OQ-7**, below).

---

## Why this gate exists (R1-F7 / S6)

FR-VCE-1 derives `view_prose.yaml` (the **words** layer) from the reqs doc cheaply because view copy is
**flat, hash-exempt prose** — `title`/`intro`/`empty`/… map one-to-one onto `### View:` keys. `display.yaml`
is the opposite: it is **hashed presentation *structure*** (column order, labels, `format`, detail sections,
FK label resolution). The risk the gate guards against: assuming structure is as derivable as words, and
silently baking **guessed** structure into a **hashed** manifest — where a wrong guess is not a cosmetic
miss but a structural defect that also trips `--check` drift. So `display.yaml` must **not** ride
FR-VCE-1's coattails; it earns emission only for fields the reqs grammar can author **without guessing**.

## What the reqs grammar actually carries

- **`### Entity`** — a `Field | Type | Required | Notes` table + controlled relationship sentences. Field
  *order* in the table is incidental (authoring convenience), **not** a declared display contract; `Notes`
  is freeform prose, not a column label. No marker exists for hidden/sort/section/label intent.
- **`### View:`** — `Kind / Root / Shows / Compute / Scope / Route` + the copy keys. No presentation
  *binding* (no `root_label_field`, no relation `via_fk` / `label_field`).

## The table

`display.yaml` schema is `EntityDisplay` (+ `ColumnDisplay`, `DetailSection`) and `ViewDisplay`
(+ `RelationDisplay`) in `backend_codegen/display_manifest.py`.

| `display.yaml` field | Layer | Authored in reqs grammar? | $0-derivable without guessing? | Verdict |
|---|---|---|---|---|
| `EntityDisplay.entity` | identity | yes (`### Name`) | yes — it's the entity name | **identity only** (no display value) |
| `EntityDisplay.title` | structure | no | no — entity name is *already* the generator default; a custom title is new copy | **needs authoring** |
| `EntityDisplay.subtitle` | structure | no | no | **needs authoring** |
| `EntityDisplay.label_field` | structure (hashed) | no | **heuristic only** (first non-id string / a `name`/`title` field) — a *guess* | **needs authoring** (guess unsafe on hashed structure) |
| `EntityDisplay.columns[].field` (order) | structure | incidental table order | no — table order is not a declared contract | **needs authoring** |
| `ColumnDisplay.label` | structure | no (`Notes` is freeform) | no | **needs authoring** |
| `ColumnDisplay.format` | structure | no | no | **needs authoring** |
| `EntityDisplay.sections` | structure | no | no | **needs authoring** |
| `EntityDisplay.hidden_fields` | structure | no (no hidden marker) | no | **needs authoring** |
| `EntityDisplay.default_sort` | structure | no | no | **needs authoring** |
| `ViewDisplay.root_label_field` | binding (hashed) | no | heuristic only — a guess | **needs authoring** |
| `RelationDisplay.via_fk` | binding | the FK is in the schema | the FK is derivable, but *binding it as a display label* is new intent | **needs authoring** |
| `RelationDisplay.label_field` | binding (hashed) | no | heuristic only — a guess | **needs authoring** |

**Derivable subset = `{entity name, view name}` — identity only, zero presentation value.** Emitting a
`display.yaml` containing only identity keys is a no-op: byte-identical to emitting nothing (the generator
already defaults every structural field). So extraction emits **nothing**.

## Decision (the gate's rule, applied)

> *"If any required field needs new authoring, FR-VCE-4 splits to its own increment/OQ."*

Every value-carrying field needs new authoring → **FR-VCE-4 splits**. Manifest-extraction does **not** emit
`display.yaml`; `generate schema --with-manifests` is unchanged. The heuristic `label_field` guess, if ever
wanted, belongs in the **generator's runtime defaults** (where a label fallback already lives), **not** baked
into an extracted *hashed* manifest — keeping the bucket-1 structure deterministic and guess-free.

## OQ-7 (new, split out)

**OQ-7 — Should `display.yaml` get a dedicated authoring surface in the reqs grammar?** A separate
increment would add explicit display keys to the `### Entity` / `### View:` blocks (e.g. a `Label by:` line,
a `Columns:` order line, a `Sections:` grouping, per-relation `show … as …`) and a matching
`extract_display()`. This is **richer authoring than view-copy**, hashed (structural), and lowest-urgency —
deferred until a project actually needs authored display structure that the generator defaults don't cover.
