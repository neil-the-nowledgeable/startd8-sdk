# Entity-Backed Board (view archetype) — Requirements

**Version:** 0.1 (Draft)
**Date:** 2026-06-08
**Status:** Draft — for SDK-team build
**Scope:** A new `board` archetype variant that **groups by a related entity's rows, ordered by that
entity's `position` field** — vs. today's `board`, which groups by a scalar on the root with a
**static `order` string list**. This is the `$0` path for a board whose columns are **runtime data**
(user-defined), not a compile-time enum.
**Requested by:** the StartDate (strtd8) app team — surfaced by the P3 **custom-stages** decision.
**Goal in their words:** *maximize deterministic ($0) generation; minimize owned-glue.*
**Related:**
- strtd8 `docs/kickoff/PIPELINE_REQUIREMENTS_v0.2-draft.md` §8 (the ask is *named* there but not
  specced): user-definable funnel stages (`PipelineStage` entity) → FR-36 board can't use the
  static-`order` archetype → it fell to owned-glue. This archetype returns FR-36 to `$0`.
- `src/startd8/view_codegen/manifest.py` / `renderers.py` — the existing `board` archetype + the
  `scope:` (AR-3/AR-1) and `compute:` (AR-2) grammar precedents this mirrors
- `src/startd8/view_codegen/renderers.py::_render_board` — the static-`order` board this generalizes

---

## 1. Problem

The `board` archetype groups root rows by `getattr(root, group_by)` and orders the columns by a
**static `order: [...]` string list** baked into `views.yaml` at generation time
(`_render_board`). That works only when the column set is a **compile-time constant** (a Prisma
enum). When the columns are **user-defined runtime rows** — the P3 `PipelineStage` case (the user
adds/renames/reorders stages at runtime) — there is no static list to bake: the columns and their
order are only known by querying the related entity. So such a board today must be **owned-glue**
(a hand-authored view), losing the `$0` guarantee.

## 2. The archetype

A `board` whose columns come from a **related entity's rows, ordered by a numeric `position`
field**, with root rows grouped by a foreign-key reference to that entity.

- **Columns** = `SELECT * FROM <ColumnEntity> ORDER BY <position_field>` at request time.
- **Grouping** = each root row joins to its column by `root.<ref_field>` == `ColumnEntity.id`.
- **Order** = the column entity's `position` field (not a static list).
- Root rows whose `ref_field` matches no column row are kept in an "unassigned" tail (no row lost —
  same no-row-lost guarantee as the static board).

## 3. Functional requirements

- **FR-EB-1 — Manifest grammar for an entity-backed board.** `views.yaml` `kind: board` gains a
  variant declaring (a) the **column entity**, (b) the **root→column reference field**, and (c) the
  column entity's **order field**. Mirror the existing grammar style (AR-3 `scope:` / AR-2
  `compute:`): a small, closed, parser-validated set of keys. Strawman:
  ```yaml
  - name: pipeline_board
    kind: board
    root: Opportunity
    group_by: stageId          # the root's FK-ish ref to the column entity
    columns_from: PipelineStage # the column entity (its rows ARE the columns)
    order_by: position          # the column entity's ordering field
  ```
  The static-`order` board (today's form: `group_by` a scalar + `order: [...]`) stays valid and
  **byte-identical** — the entity-backed variant is selected only when `columns_from` is present.
  Loud-fail (no silent drop): `columns_from` naming a non-entity, `order_by` not a field on it,
  `group_by` not a field on the root, or mixing `order:` with `columns_from:`.

- **FR-EB-2 — Generated data fn queries columns at request time.** The emitted `<view>_data(session)`
  reads `columns_from` rows ordered by `order_by`, groups `root` rows by `group_by`, and returns
  columns in the entity's order with an unassigned tail. No static order list is emitted. Verify:
  against seeded `PipelineStage` rows (positions 1..N) + Opportunities, the data fn returns columns
  in `position` order, each holding its grouped roots; reordering a `PipelineStage.position` row
  reorders the columns with no regeneration.

- **FR-EB-3 — Reuse the seam + render conventions.** Mounts through the owned `user_routers` seam
  (views never self-mount); request-first `TemplateResponse`; two-hash drift header; registered for
  `--check`; an empty board (no columns or no roots) renders the declared empty state, never errors.

- **FR-EB-4 — Idempotent + parity.** Byte-stable re-render; existing static-board manifests render
  byte-identically (regression-guarded). The emitted module + template + test parse clean (AST) and
  the emitted runtime test runs green against generated tables.

## 4. Acceptance

- The strtd8 P3 board (FR-36): `root: Opportunity`, `columns_from: PipelineStage`,
  `group_by: stageId`, `order_by: position` generates a `$0` board — **FR-36 returns from owned-glue
  to `$0`**.
- Reordering / renaming / adding a `PipelineStage` row changes the board's columns with **no
  regeneration** (the columns are data).
- The existing static-`order` board (e.g. a status enum) is unchanged, byte-identical.

## 5. Non-requirements

- **Not** a replacement for the static board — both coexist; `columns_from` selects the variant.
- **No** drag-to-reorder UI in v1 (the columns reflect `position`; editing position is plain CRUD on
  the column entity, the FR-40 stage-management surface).
- **No** cross-entity aggregation beyond grouping (counts/metrics stay the `dashboard`/computed-panel
  archetypes' job).

---

*Draft 0.1 — fills the requirement gap the strtd8 P3 §8 custom-stages decision named ("a new SDK
entity-backed board archetype would return FR-36 to `$0`") but did not spec. Mirrors the AR-2/AR-3
manifest-grammar precedents; the existing static-`order` board is preserved byte-identically.*
