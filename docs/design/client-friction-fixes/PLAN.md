# Client-Logged Friction Fixes — Implementation Plan

**Version:** 1.0 (post-planning, paired with REQUIREMENTS v0.2)
**Date:** 2026-07-09
**Branch:** `fix/client-friction-triage-p0p2`

Sequenced by (1) severity and (2) dependency. Each step names the edit locus, the change, and the
regression test that must fail on `main` and pass after (FR-0). All loci re-verified this session.

---

## Sequencing rationale

1. **P0 codegen first** (F13, F3b) — highest severity (silent data corruption), smallest blast radius,
   two files, no cross-module dependencies.
2. **F3b before F3** — F3 (`has one`) needs `@unique` to actually reach `tables.py` to be
   end-to-end verifiable; F3b provides that emission.
3. **P1 crashes** (F2, H3) — localized `view_codegen` guards.
4. **F1/F8** — extraction sanity check (touches `manifest_extraction` + `cli_kickoff`).
5. **P2 honesty** (H4, H5) — VIPP disposition + observability wiring; independent, can parallelize.

---

## Step 1 — FR-F13: `yes/no` boolean defaults

**1a. Renderer (defensive).** `src/startd8/backend_codegen/sqlmodel_renderer.py`,
`_default_field_arg` (line 65). Before the numeric/bareword fallthrough (line 93-97), add:
```python
if field.type == "Boolean" and val in ("yes", "no"):
    return f"default={'True' if val == 'yes' else 'False'}"
```
Place it alongside the existing `("true", "false")` branch (line 93). Gate on `field.type ==
"Boolean"` so a `String @default(yes)` (a legit enum member) is untouched.

**1b. Emitter (canonical).** `src/startd8/manifest_extraction/prisma_emitter.py` — where a
`yes/no … default:` boolean field is emitted. Emit `@default(false)` / `@default(true)` instead of
`@default(no|yes)`. (Locate the boolean-default emission; confirm the prose→default mapping.)

**Regression test:** `tests/unit/backend_codegen/test_sqlmodel_renderer.py` — a schema with
`active Boolean @default(no)` must render `Field(default=False)` (not `default="no"`). Add a matching
emitter test that `yes/no default: no` prose emits `@default(false)`. Assert on `main` the render is
`default="no"`.

---

## Step 2 — FR-F3b: emit `@unique` / `@@unique`

**2a. Field-level `@unique`.** `sqlmodel_renderer.py`, `_render_table_field` (line 253). The function
already composes `args` from `is_pk`/`fk`/`default_arg` (line 279-285). Add:
```python
if field.is_unique and not is_pk:   # PK is already unique
    args.append("unique=True")
```
`PrismaField.is_unique` already exists (`prisma_parser.py:62`). No signature change needed.

**2b. Model-level `@@unique`.** Composite uniqueness lives in `PrismaModel.block_attributes` /
`compound_unique_keys` (`prisma_parser.py:100-110`). In the **table-class** renderer (the function
that emits `class X(SQLModel, table=True)` and already handles compound `@@id` via
`_compound_pk_cols`), add a `__table_args__` line when `compound_unique_keys` (excluding any that
equal the compound PK) is non-empty:
```python
__table_args__ = (UniqueConstraint("assignmentId", name="uq_review_assignmentId"),)
```
Requires importing `UniqueConstraint` from `sqlalchemy` in the generated file's imports (thread a
`needs.add("uniqueconstraint")` and add the import line to the import emitter, mirroring the existing
`Column`/`JSON` import handling). Skip any compound-unique tuple identical to the model's `@@id`.

**Regression test:** `tests/unit/backend_codegen/test_sqlmodel_renderer.py` — (i) `email String
@unique` → `Field(..., unique=True)`; (ii) `@@unique([assignmentId])` → `__table_args__` with
`UniqueConstraint`; (iii) a `@@unique` equal to `@@id` emits **no** duplicate constraint;
(iv) idempotency `--check` unchanged for schemas with no unique (FR-0b).
**Lesson note (Testing #9):** these tests instantiate SQLModel tables → SQLModel's process-global
`MetaData` survives `sys.modules` purges. Drop owned tables at setup **and** teardown (scoped
`md.remove`, not `md.clear`) to avoid a cross-test collision / false-green.

---

## Step 3 — FR-F3: `has one` one-to-one (gated by OQ-4)

**Decision needed (OQ-4).** Two landing options:
- **Minimal (recommended if time-boxed):** FR-F3-iii only — in the grammar/extraction, when verb ==
  `has one`, emit a `kickoff check` warning `has-one-unsupported` (no silent has-many). Small, honest.
- **Full:** thread verb cardinality end-to-end.

**Full-support edits:**
- `src/startd8/manifest_extraction/entities.py:409` — split `has one` from `has many`; carry a
  `cardinality="one"` signal on the relation record (line 421 currently builds the same FK value for
  both).
- `src/startd8/manifest_extraction/prisma_emitter.py` — for a `cardinality="one"` relation, emit the
  parent side as singular (`X?`) and add `@unique` to the child FK scalar. With Step 2 (FR-F3b) this
  becomes a real DB constraint.

**Regression test:** extraction golden — `an Assignment has one Review` produces `review Review?`
(singular) with `@unique` on `Review.assignmentId`; end-to-end, the generated `tables.py` has
`unique=True` on the FK (depends on Step 2). On `main`, assert it emits `reviews Review[]`.

---

## Step 4 — FR-F2: `board` empty-order → clear error

**4a. Parse-time guard (guaranteed).** `src/startd8/view_codegen/manifest.py` — in `parse_views`
(order defaulted at line 447) or `ViewSpec` post-init, when `kind == "board"` and `order` is empty:
```python
raise ValueError(f"board {module!r}: group_by {group_by!r} requires an Order: (declared enum values)")
```
**4b. Test-emitter guard (defense-in-depth).** `src/startd8/view_codegen/renderers.py:1550` — the
crash site. With 4a no board spec reaches it empty, but add an explicit guard so the emitter never
does an unguarded `v.order[0]`.

**4c. (OQ-5/FR-F2b, optional).** If `parse_views` is given `known_enums`, default `order` to the
group-by enum's values. Only if it threads cleanly from the caller (`cli`/generate views), which
already has the parsed schema/enums.

**Regression test:** `tests/unit/view_codegen/test_*` — a `board` view, enum `group_by`, no `order`
→ `ValueError` naming the view (not `IndexError`). On `main`, assert `IndexError` is raised (the bug).

---

## Step 5 — FR-H3: `workspace` non-polymorphic → clear error

`src/startd8/view_codegen/renderers.py:150-152` — replace:
```python
p = v.polymorphic
assert p is not None
```
with:
```python
p = v.polymorphic
if p is None:
    raise ValueError(
        f"workspace {v.module!r}: requires a polymorphic relation "
        f"(of/type_field/id_field/type_map); root {v.root!r} has none"
    )
```
(Consider validating at `parse_views` too, mirroring Step 4a, so it fails at spec-load not render.)

**Regression test:** a `workspace` view with a non-polymorphic root → `ValueError` naming the view.
On `main`, assert bare `AssertionError`.

---

## Step 6 — FR-F1/F8: choice-of value-level sanity + docs

**6a. Extraction signal.** `src/startd8/manifest_extraction/entities.py:237` (after `enum_values`
computed, before the field record is appended, ~237-253): when the field is `choice of:` and
`len(enum_values) == 1`, emit an extraction record `choice-of-single-value` keyed to
`Entity.field` (suspicious truncation). Decide hard-vs-warn per **OQ-7**.

**6b. kickoff check surfacing.** `src/startd8/cli_kickoff.py` — ensure `_is_conformance_failure`
(line 51-56) treats the new record appropriately (hard failure under `--strict` if OQ-7 = hard;
otherwise a printed warning that keeps exit 0 but is visible).

**6c. Docs.** Update the FORMAT worked example to show `choice of:` **inside a table** with
`\|`-escaped pipes (FR-F1b). Optionally (FR-F1c) detect an unescaped in-table `choice of:` `|` in
`grammar.md_tables` (`grammar.py:101-126`) and warn.

**Regression test:** a REQUIREMENTS-format doc with `| status | choice of: a\|b\|c |` inside a table,
unescaped, extracting to a single value → `kickoff check` reports `choice-of-single-value` (not "docs
conform"). On `main`, assert `kickoff check` reports conform (the false-green bug).

---

## Step 7 — FR-H4: VIPP entity-field capture disposition honesty

**Edit:** `src/startd8/vipp/evaluate.py` (~199-205, the ACCEPT return). A `capture` proposal whose
value-path is a `<Entity>.<field>` symbol that VIPP validated via FIELD_AUTHORITY, but which has **no
writable target** in the kickoff manifest, must be adjudicated **ACCEPT-but-inert** — carry a
qualifier/reason (`value_path_not_allowed` / `not-mapped-to-kickoff-inputs`) so the disposition does
not imply an applicable write. (Per FR-H4c / NR-4, do **not** touch `proposals.py`/`manifest.py` to
widen the floor.)

Decide the exact disposition per **OQ-5** (ACCEPT-but-inert vs OMIT-with-reason).

**Regression test:** `tests/unit/vipp/test_evaluate.py` — a `capture` of `Chore.name` (a real field)
adjudicates to the inert/qualified disposition, and a full negotiate→apply run reports it as **inert,
not `wrote 1/2`**. On `main`, assert negotiate returns a plain ACCEPT[VALIDATED] that apply then
refuses (the dishonest split).

---

## Step 8 — FR-H5: observability.yaml wiring

**8a. SDK-side (in-repo).** `scripts/generate_observability_artifacts.py`:
- Add `--observability-yaml` argparse flag (optional, mirror `--manifest` at line 64-68).
- Thread `observability_yaml_path=Path(args.observability_yaml) if args.observability_yaml else None`
  into both `generate_observability_artifacts(...)` call sites (~142, ~173). The function already
  accepts the parameter (line 426).

**8b. Cross-repo (tracked separately, FR-H5b).** `~/Documents/dev/cap-dev-pipe/pipeline/stages/
observability.py:32-86` — add `observability_yaml_path` to `run_observability()` and pass it to
`generate(...)`. **This is the canonical cap-dev-pipe repo (symlinked)** — land as its own change
with its own branch/PR, not folded into this SDK PR.

**8c. Docs (FR-H5c).** Update `NEXT_STEPS` / `O11Y_CORE_BUILD_RUNBOOK` to state the real contract and
the precedence rule chosen in **OQ-6** (override vs merge).

**Regression test:** `scripts/` or unit test — invoking the generator with `--observability-yaml`
threads the path to `generate_observability_artifacts` (assert the param is received/consumed). Doc
change verified by inspection.

---

## Verification gate (before merge)

- [ ] Each step's regression test **fails on `main`**, **passes on branch** (FR-0).
- [ ] `pytest tests/unit/backend_codegen tests/unit/view_codegen tests/unit/vipp` green.
- [ ] `generate backend --check` / `generate views --check` idempotency unchanged on a schema that
      does **not** exercise any fix (FR-0b) — no drift.
- [ ] Run the two P0 fixes against the **portal-rebuild** and **household-o11y** schemas that
      originally logged them; confirm the friction no longer reproduces.
- [ ] `ruff check src/` + `black src/` clean on edited files.
- [ ] Branch-first → PR (never commit to `main`); Stage-7 (FR-H5b) filed as a separate cap-dev-pipe PR.

---

## Effort estimate

| Step | Files | Size | Risk |
|------|-------|------|------|
| 1 (F13) | 2 | S | low |
| 2 (F3b) | 1 (+import emitter) | M | low-med (import threading) |
| 3 (F3) | 2 | M (full) / S (flag-only) | med — **OQ-4** |
| 4 (F2) | 1-2 | S | low |
| 5 (H3) | 1 | S | low |
| 6 (F1/F8) | 2-3 | M | med — **OQ-7** false-positive tuning |
| 7 (H4) | 1 | S-M | med — **OQ-5** disposition semantics |
| 8 (H5) | 1 in-repo (+1 cross-repo) | S | low (in-repo) |

Recommended first landing: **Steps 1, 2, 4, 5** (the four P0/P1 codegen fixes — smallest, highest
severity, no open questions). Steps 3/6/7 carry open questions to resolve (or CRP) first; Step 8 is
independent and low-risk.
