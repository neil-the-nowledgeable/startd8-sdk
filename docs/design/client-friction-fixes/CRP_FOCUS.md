# CRP Focus — Client-Friction Fixes (deferred, open-question steps)

Weight the review on the three **least-reviewed** steps; the P0/P1 codegen fixes are already
implemented and merged (PR #175) and are **out of scope** for this review.

## Where we need input most

### 1. FR-F3 / Step 3 — `has one` full one-to-one support
`has one <X>` currently emits `X[]` (one-to-many) because the grammar
(`manifest_extraction/entities.py:409`) treats `has one` and `has many` identically, and the
Prisma emitter decides cardinality by FK ownership, not the verb. OQ-4 is resolved to **full
support**: thread a `cardinality="one"` signal end-to-end → singular relation (`X?`) + `@unique` on
the child FK (which, with the now-merged F3b, becomes a real DB constraint).
- **Press on:** self-relations, optional-vs-required one-to-one, existing schemas that already say
  `has many`, and whether adding `@unique` to a child FK can silently break existing many-row data.
  Is the flag-as-unsupported fallback (FR-F3-iii) the safer first landing?

### 2. FR-F1/F8 / Step 6 — in-table `choice of:` truncation + kickoff-check sanity (OQ-7)
The Markdown table splitter breaks `| status | choice of: a|b|c |` at the first `|`, so the enum
extracts to a single value; `kickoff check` reports "docs conform" (false-green). Fix adds a
value-level `choice-of-single-value` signal keyed to `Entity.field`.
- **Press on OQ-7:** should a multi-value `choice of:` that extracts to ONE value be a **hard**
  `kickoff check --strict` failure (exit non-zero) or a **warning**? Hard is safer for silent data
  loss but false-positives on a legitimately single-value closed vocabulary. What disambiguates a
  truncation from a genuine single-member enum?

### 3. FR-H4 / Step 7 — VIPP entity-field capture disposition honesty (OQ-5)
A `capture` of `<Entity>.<field>` (e.g. `Chore.name`) is ACCEPT[VALIDATED] at negotiate
(`vipp/evaluate.py`) but refused `value_path_not_allowed` at apply (`proposals.py:308-311`), because
VIPP's FIELD_AUTHORITY namespace (`Chore.name`) differs from the kickoff apply-floor allow-list
namespace (`conventions.yaml#/language`). Reframed (NR-4): do **not** widen the floor; make the
disposition honest.
- **Press on OQ-5:** ACCEPT-but-inert (carry a `value_path_not_allowed`/`not-mapped` qualifier) vs
  OMIT-with-reason at negotiate? Which reads more honestly in the disposition report and avoids the
  "wrote 1/2" silent-partial? Is there a third disposition the VIPP model already supports?

## Settled — do NOT relitigate
- H1 (wireframe `KeyError 'api'`) and H2 (MCP `questionary`) are **already fixed** (NR-1).
- F13, F3b, F2, H3 are **implemented + merged** (PR #175) — out of scope.
- Widening the kickoff apply-floor allow-list to entity-field paths is **rejected** (NR-4 / FR-H4c).
- P3 DX findings (F4–F11) are **deferred** (NR-2).

## Also weigh
- **OQ-6** (Step 8): should authored `observability.yaml` **override** the manifest when present, or
  **merge** (and with what precedence)? The generator already accepts the param; only wiring +
  precedence is undecided.
- Cross-cutting **FR-0**: every fix must ship a regression test that fails on `main`. Flag any
  proposed step that lacks a clear failing-first test.
