# startd8 SDK — Feedback from a systematic portal rebuild

**From:** the Benchmark Reviewer Portal rebuild (`portal-rebuild` branch)
**Date:** 2026-07-08
**Context:** We rebuilt a working app the SDK's *systematic* way — kickoff input package →
`REQUIREMENTS.md`/`PLAN.md` in the extraction FORMAT → `startd8 generate contract` → the `$0`
cascade → port the hand-written integration layer. The app works end-to-end (INT-1..8 verified).
This doc records the **hand-work and workarounds** that point at concrete SDK improvements, plus
what worked well. Findings are ordered by value to the SDK team; each cites where it bit us.

---

## The rebuild in one line
Same running app as the original hand-built portal, but this time the schema + manifests + pages
flow **deterministically from prose** (re-derivable, gated). Getting there surfaced ~11 friction
points; none were blockers, all are fixable.

---

## High-value findings

### F1 — `choice of: a|b|c` inside a Markdown table silently truncates the enum
- **Symptom:** every enum extracted with only its **first** value, e.g.
  `AssignmentStatus = ['not_started']` (should be `not_started|in_progress|submitted`).
- **Cause:** the `|` in `choice of: A|B|C` collides with the Markdown table column separator, so the
  `| status | choice of: … |` cell is split.
- **Caught by:** `generate contract --check` parity (`values ['not_started'] (emitted) vs [...] (live)`) —
  **not** by `kickoff check`, which reported *"0 to fix — docs conform"*.
- **Workaround:** escape every pipe as `\|` inside the field-table cell.
- **Suggested fix:** (a) have extraction/`kickoff check` detect an in-table `choice of:` with unescaped
  `|` and warn (or auto-unescape); (b) show the `\|` escaping in the FORMAT worked example — today the
  sample (`choice of: draft|active`) is shown *outside* a table, so it doesn't warn the author.
- **Impact:** silent data loss on every choice field; only a second, different gate caught it.

### F2 — `board` view crashes `generate views` (uncaught `IndexError`) without an explicit `Order:`
- **Symptom:** `IndexError: tuple index out of range` in `render_views` — not the `ValueError`
  ("malformed views.yaml") path, so the error message is a raw traceback.
- **Repro:** a `board` view whose `group_by` is an enum field, with no `order`.
- **Workaround:** add `Order: <enum values>` (→ `order: [...]` in views.yaml).
- **Suggested fix:** derive the board's column order from the group-by enum's declared values
  automatically; if that's not possible, raise a clear
  `board '<name>': group_by '<field>' requires an Order:` instead of an IndexError.
- **Impact:** hard crash that blocks the cascade; unhelpful error.

### F3 — `has one` is not honored → becomes one-to-many
- **Symptom:** `an Assignment **has one** Review` produced `reviews Review[]` (a list) with a
  **non-unique** `assignmentId` FK — i.e. one-to-many, not one-to-one.
- **Workaround:** the integration adapts (`_first_review(a) = a.reviews[0] if a.reviews else None`);
  the intended uniqueness (at most one review per assignment) is lost at the schema level.
- **Suggested fix:** map `has one` to a singular relation field + `@unique` on the child FK. If it's
  not yet supported, `kickoff check` should flag `has one` as unsupported rather than silently emit
  has-many.
- **Impact:** modeling correctness + forces list-handling in every consumer of the relation.
- **Update (fix applied):** hand-correcting the schema to `review Review?` + `@unique` on
  `Review.assignmentId` and regenerating **did restore the singular relation** (`a.review` works,
  the `_first_review()` workaround was removed) — but see **F3b**: the `@unique` was silently
  dropped by the backend generator, so DB-level uniqueness is still not enforced.

### F3b — the backend generator drops `@unique` / `@@unique` (no unique constraints emitted)
- **Symptom:** neither field-level `@unique` (on `Review.assignmentId`) nor model-level
  `@@unique([assignmentId])` produced anything in `tables.py` — no `unique=True` on the `Field`,
  no `UniqueConstraint` / `__table_args__`. Same for the pre-existing `@unique` on
  `BenchmarkCell.cellId`, `Reviewer.email`, `Role.key`.
- **Consequence:** the generated SQLModel tables have **no unique constraints at all**; apps that
  need uniqueness (idempotent upsert by `cellId`/`email`, one-review-per-assignment) rely entirely
  on **application-level query-then-insert**, not the DB.
- **Suggested fix:** emit `Field(..., unique=True)` for `@unique` and a
  `__table_args__ = (UniqueConstraint(...),)` for `@@unique`.
- **Impact:** high for data integrity; currently every "unique" in the contract is advisory.

---

## Medium-value findings

### F4 — Per-field enum naming; no way to declare/reuse a shared named enum
- **Symptom:** the same closed vocabulary on several fields yields **separate** enums:
  `Role.key → RoleKey`, `Assignment.roleKey → AssignmentRoleKey`,
  `RubricDimension.roleKey → RubricDimensionRoleKey` — three enums, identical values;
  `Review.disposition → ReviewDisposition` (entity-prefixed).
- **Workaround:** consumers import the per-entity names; owned code that shared one `Disposition`/
  `RoleKey` had to rename its imports.
- **Suggested fix:** allow declaring a named enum once and referencing it across fields (e.g. a
  `## Enums` block, or `choice of RoleKey: SE_MANAGER|…`), emitting a single shared enum type.
- **Impact:** enum duplication in the contract; import churn in the integration layer.

### F5 — Relationship + FK field names are verbose and non-customizable
- **Symptom:** derived names differ from the natural short names a hand-author picks:
  `files→generatedFiles`, `cells→benchmarkCells`, `scores→reviewScores`,
  `roundId→reviewRoundId`, `dimensionId→rubricDimensionId`, and the Adjudication resolver FK became
  a generic `reviewerId` (the "resolver" role-name is lost).
- **Workaround:** rename ~7 relationship/FK accessors across the owned integration layer to match —
  this *was* essentially the entire cost of "port the owned layer."
- **Suggested fix:** support an optional relationship/FK name hint in prose (e.g. "an Adjudication
  belongs to a Reviewer **as** resolver"), or document the derivation rules prominently so
  integrators name against them from the start.
- **Impact:** the dominant friction for any hand-written integration built on a derived contract.

### F6 — `--with-manifests` writes `app.yaml` in the wrong place with a wrong `persistence.path`
- **Symptom:** `generate contract --with-manifests` emitted `prisma/app.yaml` (the convention
  location is the project-root `app.yaml`) and set `persistence.path: sqlite` — a **non-path literal**
  derived from the `## Scaffold & runtime | database | sqlite` row.
- **Workaround:** keep the root `app.yaml` authoritative (real `persistence.path: ./data/portal.db`),
  delete the derived `prisma/app.yaml`.
- **Suggested fix:** emit `app.yaml` at the convention root, and map the "database" setting to a valid
  `persistence.path` (file path / DSN) or a distinct `database:` key — never `persistence.path: sqlite`.
- **Impact:** duplicate + contradictory app manifests; the derived one is incorrect.

### F7 — `generate backend --pages` requires content files to pre-exist; it doesn't stub them
- **Symptom:** `error: pages.yaml: content file not found for '/': app/pages/home.md`.
- **Workaround:** author the `.md` files before running the cascade.
- **Suggested fix:** per `KICKOFF_CONTENT_INPUTS` FR-G1 (SDK-emitted stubs default to `placeholder`),
  `--pages` should emit minimal bucket-2 placeholder stubs for missing content and mark them
  placeholder — rather than erroring. Otherwise, the docs should state the `.md` files are a
  prerequisite of `--pages`.
- **Impact:** blocks the cascade; contradicts the "SDK ships throwaway placeholder content" model.

### F8 — `kickoff check` "docs conform" ≠ correct extraction
- **Symptom:** `kickoff check --strict` said *"0 to fix — docs conform"* while F1 was silently
  truncating enums. The value-completeness problem was only caught later by
  `generate contract --check`.
- **Suggested fix:** `kickoff check` should add value-level sanity checks (e.g. a multi-value
  `choice of:` that extracts to a single enum value is suspicious), not just grammar-anchor
  conformance — so the authoring gate isn't falsely green.
- **Impact:** false confidence from the first gate; only the second gate is trustworthy today.

### F13 — `yes/no` field defaults become truthy **string literals**, not booleans
- **Symptom:** `isOperator yes/no default: no` derived `isOperator Boolean @default(no)` in Prisma,
  which the backend generator turned into `isOperator: bool = Field(default="no")` — the Python
  value is the **string `"no"`, which is truthy**. So a Reviewer created without setting the field
  would default to **operator = true**. Same shape for `active @default(yes)` and `locked @default(no)`.
- **Where:** the `## Entities` `yes/no … default: no|yes` mapping → Prisma `@default(no|yes)` →
  SQLModel `Field(default="no"|"yes")`.
- **Mitigation here:** the seeder sets `isOperator` explicitly, so it never hits the bad default.
- **Suggested fix:** map `yes/no` defaults to real booleans — `@default(false)` / `Field(default=False)`
  — not the `no`/`yes` string tokens.
- **Impact:** a silent security-relevant default (operator-by-default) if any consumer relies on it.

---

## Low-value / already-known

### F9 — `--gate` (compileall) is syntax-only → false confidence for import errors
After regen renamed enums, `--gate` passed (compileall doesn't resolve imports) even though an owned
file imported the old `Disposition`; only an actual boot / `--boot-smoke` caught it. Worth stating
plainly in the gate docs that `--gate` ≠ "it runs."

### F10 — Workbook board UID/name derives from the folder name
`kickoff portal` produced `cc-portal-kickoff-internal` / title *"internal"* because the project root
folder is `portal/internal`. `--project <name>` overrides it. Suggest defaulting from
`pipeline.env` `PROJECT_NAME` / `app.yaml` `app.name` before the folder name (folder names like
`internal` are generic and collision-prone).

### F11 — `deployed` mode blocks a SQLite file (sensible guardrail, worth a callout)
`generate backend` with `deployment.mode: deployed` over a SQLite file hard-errors (needs a Postgres
DSN + `deploy.trust_gateway` + tenancy). Correct, but the local-dev answer is "use `installed` mode"
— a one-line note in the deployed-mode docs would save a round-trip.

---

## What worked well (keep these)
- **The `$0` authoring loop is genuinely good.** `kickoff check` converged our docs 13 → 6 → 2 → 1 → 0
  fixes with zero LLM cost — a tight, honest feedback loop.
- **Layered gates caught the real bug.** `generate contract --check` parity flagged the enum
  truncation the authoring gate missed — the belt-and-suspenders design paid off.
- **Deterministic cascade at scale.** ~100 files (backend + scaffold + views + pages) generated
  reproducibly from one prose spec.
- **The owned-composition seam is excellent.** Everything in `app/user_routers.py` +
  non-generated modules (`portal_ext.py`, `portal_auth.py`, `portal_templates/`, `scripts/`)
  survived every regeneration untouched. The only churn was adapting to renamed schema symbols
  (F4/F5), never the seam itself.
- **Workbook + confirm/assess + stakeholder panel** are strong additions — the field-level
  `kickoff confirm` provenance loop and the Grafana Workbook made kickoff state legible.

---

## Donation candidates (built + working in this repo, ready to lift into the SDK)

Two pieces we built on top of the SDK's `stakeholder_panel` adapter stack, designed to lift in cleanly.
Spec: `docs/ROSTER_COMPOSITION_REQUIREMENTS_v0.2.md` + `docs/ROSTER_COMPOSITION_PLAN_v1.0.md`.
Code: `scripts/compose_roster.py` + `config/panel_roster.yaml`.

### D-A — a `personas` pass-through adapter (built-in beside `role-rubric`)
A one-method adapter that makes an already-PersonaBrief-shaped file a first-class source:
```python
class PersonasAdapter:
    name = "personas"
    def adapt(self, text): return AdaptResult(roster=parse_roster(text), warnings=[])
```
Register it as a **lazy built-in** in `adapters/__init__.py._BUILTINS` (next to `role-rubric`) so
`panel import --format personas SOURCE` works and multi-source composition can delegate to it. Today
the composer `register()`s it at runtime — a built-in removes that step.

### D-B — `panel compose --config` (multi-source roster composition)
The SDK already has the registry + `ingest()` + `validate_roster()` — the only missing piece is
**merging N ingested sources under a declared policy**. A config declares `sources: [{format, source}]`
plus a `merge` policy (`dedup_key`, `on_conflict: error|first-wins|last-wins`, `order`); the composer
ingests each source through its adapter, merges `roster.personas` per policy, validates via
`validate_roster`, and serializes with a provenance header — reusing everything, no new
envelope/validation code. `config/panel_roster.yaml` + `scripts/compose_roster.py` are the working
reference; `startd8 panel compose --config <file>` is the suggested surface. Verified: reproduces our
14-persona roster (5 `role-rubric` + 9 `personas`), fail-closed on unknown adapter / duplicate `role_id`.

**Why donate:** it generalizes the project-specific `--extra` flag into the SDK's own idioms —
de-hardcodes the *data* (which sources) while reusing the SDK's registry *dispatch* (the exact shape
of the dev-docs "de-hardcode the data, the dispatch is already a registry" lesson).

---

## Appendix — where each finding bit us (commands)
- F1/F8: `startd8 kickoff check docs/REQUIREMENTS.md docs/PLAN.md --strict` (green) vs
  `startd8 generate contract -r docs/REQUIREMENTS.md -r docs/PLAN.md --check` (flagged truncation).
- F2: `startd8 generate views --schema prisma/schema.prisma --views prisma/views.yaml` (IndexError).
- F3/F4/F5: visible in the `prisma/schema.prisma` diff between `main` (hand-authored) and
  `portal-rebuild` (derived); the port lives in commit `07a0844`.
- F6: `startd8 generate contract … --promote --with-manifests --force`.
- F7: `startd8 generate backend … --pages prisma/pages.yaml` (content-not-found).
- F10: `startd8 kickoff portal <project> --provision …`.
