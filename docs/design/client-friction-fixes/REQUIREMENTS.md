# Client-Logged Friction Fixes — Requirements

**Version:** 0.3 (Post lessons-learned hardening)
**Date:** 2026-07-09
**Status:** Draft (pre-CRP)
**Branch:** `fix/client-friction-triage-p0p2`

**Provenance:** Friction logged by two live downstream projects, re-verified against current
source this session:
- `~/Documents/dev/household/household-o11y/concierge-friction.jsonl` (entries H1–H5)
- `docs/PORTAL_REBUILD_FEEDBACK_FROM_CONSUMER_2026-07-08.md` (findings F1–F13)

The navig8 friction log (`docs/design/kickoff/CONCIERGE_FRICTION_LOG_NAVIG8.md`, F-1..10) is
onboarding *process* friction, not SDK bugs — **out of scope** here.

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (report-based assumptions) and v0.2 (after reading current source).
> The planning pass re-verified every code claim and corrected three material assumptions.

| v0.1 Assumption (from the reports) | Planning Discovery | Impact |
|---|---|---|
| H4: fix by "widening the apply floor allow-list for validated entity-field captures" | The kickoff apply floor's allow-list is **config-YAML value-paths** (`conventions.yaml#/language`, `manifest.py:133-135`), a *different namespace* from VIPP negotiate's `<Entity>.<field>` FIELD_AUTHORITY check (`evaluate.py:75-91`). There is **no `write_target`** for project entity fields — widening is infeasible/wrong. | **FR-H4 reframed**: make the negotiate disposition honest (ACCEPT-but-inert / non-actionable), not widen a floor. |
| F2: board crash is in the view *data* renderer | The board **data** renderer (`renderers.py:81`) is already **safe** on empty `order`. The `IndexError` is only in the board **test emitter** (`renderers.py:1550`, `v.order[0]`). | **FR-F2 split**: (a) guard the test emitter; (b) validate at parse time. Auto-derive from enum needs a loader signature change (enums not threaded into `parse_views`) → optional, not the core fix. |
| H5: `observability.yaml` needs a new generator parameter | `generate_observability_artifacts()` **already accepts** `observability_yaml_path` (`scripts/generate_observability_artifacts.py:426`); it is simply **never wired** by the CLI or Stage 7. Stage 7 lives in the **canonical `cap-dev-pipe` repo** (symlinked), so that half is cross-repo. | **FR-H5 narrowed**: SDK-side = add the script flag + thread the two `generate(...)` calls (in-repo, low-risk). Stage-7 wiring is a **separate cross-repo task** (or documented as manifest-SSOT). |
| F13: fix the SQLModel renderer | Root cause is upstream too: the Prisma **emitter** turns `yes/no default: no` into `@default(no)` (a bareword). A hand-authored schema hits the same renderer bug. | **FR-F13 = belt-and-suspenders**: fix the emitter (source) *and* make the renderer defensive (gate on `Boolean`). |
| F3 (`has one`) and F3b (`@unique` dropped) are separate | They are **two halves of one-to-one**: F3 must get `@unique` onto the child FK *in the schema*; F3b must carry `@unique` *from schema into `tables.py`*. Neither alone enforces uniqueness. | Sequence F3b first (schema→table), then F3 (prose→schema); F3's regression test depends on F3b's emission. |
| F2 auto-derives board order from the group-by enum | The loader `parse_views(text, *, known_entities, known_fields)` (`manifest.py:187`) has **no enum values** in scope. Auto-derivation requires threading `known_enums`. | Auto-derive demoted to an **optional enhancement (FR-F2b)**; the guaranteed fix is flag-don't-crash. |

**Resolved open questions:**
- **OQ-1 → Fix at both layers for F13.** Emitter emits canonical `@default(false|true)`; renderer stays defensive for hand-authored schemas.
- **OQ-2 → H4 is a disposition-honesty fix, not an allow-list widening.** (See discovery above.)
- **OQ-3 → H5 SDK-side is in-scope and small; cap-dev-pipe Stage 7 is a tracked cross-repo follow-up**, not blocked on here.

---

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted `Lessons_Learned/sdk/` (Design_Docs + SDK_developer, lesson 9 Testing Patterns) before
> CRP. Applicable lessons — each changed the spec/plan:

- **[Testing #9 — regression attribution via base-commit worktree repro / "fail on main, pass on
  branch"]** → hardened **FR-0**: each regression test must be demonstrated red on `main` *before*
  the fix, not just green after. Added to the plan's per-step tests and the verification gate.
- **[Testing #9 — SQLModel process-global `MetaData` survives `sys.modules` purge (drop owned tables
  at start + teardown; scoped `md.remove`, not `md.clear`)]** → **plan Step 2 (FR-F3b) test note**:
  the `@unique`/`UniqueConstraint` tests instantiate SQLModel tables, so they must drop owned tables
  at setup+teardown to avoid the process-global metadata collision. Prevents a flaky/false-green.
- **[Testing #9 — golden-snapshot capture-lock-refactor-verify (JSON tuple→list false-fail)]** →
  **FR-0b** idempotency assertions compare rendered *text*, not re-serialized structures, to avoid
  tuple→list snapshot false-fails.
- **[Phantom-reference audit]** → every locus named in REQUIREMENTS/PLAN was re-verified to exist
  this session with an exact `file:line` + quote (H1/H2 confirmed *already fixed*, so excluded per
  NR-1). No phantom symbols remain.

**Least-reviewed target for CRP (steering memory):** the **VIPP disposition reframe (FR-H4)** and the
**`has one` grammar/emitter change (FR-F3)** — both carry open questions (OQ-4, OQ-5) and the least
prior design review. **Settled / do-not-relitigate:** H1/H2 are already fixed (NR-1); widening the
apply-floor allow-list is rejected (NR-4/FR-H4c); the P3 DX findings are deferred (NR-2).

---

## 1. Problem Statement

Five deterministic **$0-path** codegen/DX bugs and two contract-honesty gaps, all logged by real
consumers, survive the SDK's existing gates. The unifying failure mode is **silent-wrong**: the
generator emits code that compiles and runs but is *semantically incorrect* (a truthy string where a
boolean was meant; a missing DB constraint; a one-to-many where one-to-one was specified), or crashes
with a **bare, unkeyed exception** instead of a clear, actionable error. Per the SOTTO/HAYAI
principles, a $0 deterministic path must not silently corrupt data or crash without naming the
offending artifact.

| ID | Severity | Current State | Gap | Verified locus |
|----|----------|---------------|-----|----------------|
| **F13** | P0 (data/security) | `yes/no default: no` → `Field(default="no")` (truthy string) | boolean default is `True` when author meant `False` (operator-by-default) | `sqlmodel_renderer.py:91-97` + emitter |
| **F3b** | P0 (data integrity) | `@unique`/`@@unique` parsed but never emitted | tables have **no** unique constraints; uniqueness is advisory-only | `prisma_parser.py:62` (parsed) vs `sqlmodel_renderer.py:277-303` (not emitted) |
| **F1/F8** | P0 (silent data loss) | in-table `choice of: a\|b\|c` truncates to first value; `kickoff check` says "docs conform" | enum silently loses values; the first gate is falsely green | `grammar.py:111`, `entities.py:237`, `cli_kickoff.py:129` |
| **F2** | P1 (crash) | `board` view, enum `group_by`, no `Order:` → bare `IndexError` | hard crash, no view name, blocks cascade | `renderers.py:1550` (test emitter) + `manifest.py:447` (loader) |
| **H3** | P1 (crash) | non-polymorphic `workspace` root → bare `AssertionError` | hard crash, no view name | `renderers.py:150-152` |
| **F3** | P2 (modeling) | `has one` treated identically to `has many` → `Review[]` | one-to-one intent lost at schema level | `entities.py:409` (verb), `prisma_emitter.py` (cardinality) |
| **H4** | P2 (honesty) | entity-field `capture` ACCEPT[VALIDATED] at negotiate, refused `value_path_not_allowed` at apply | disposition over-promises a write that cannot happen | `evaluate.py:75-91`/`199-205` vs `proposals.py:308-311` |
| **H5** | P2 (honesty) | authored `observability.yaml` not read by shipped path | authored thresholds/SLOs silently omitted | `scripts/generate_observability_artifacts.py:426` (accepted, unwired) |

---

## 2. Requirements

### Cross-cutting

- **FR-0 (regression-first).** Every fix ships with a **regression test that fails on `main` and
  passes with the fix** — a golden that reproduces the exact consumer friction. The tests are as
  load-bearing as the fixes (these bugs slipped *because* no test covered the case).
- **FR-0a (flag-don't-crash).** Every "hard crash" fix (F2, H3) must raise a clear, typed error that
  **names the offending view/field** (RUN-029 style), never a bare `AssertionError`/`IndexError`.
- **FR-0b (idempotency preserved).** All codegen fixes must keep `generate … --check` parity /
  byte-identical idempotency on unaffected inputs (no drift on schemas that don't exercise the fix).

### P0 — silent-wrong

- **FR-F13.** A `yes`/`no` Prisma `@default` on a **`Boolean`** field must produce a real Python
  boolean.
  - **FR-F13a (renderer, defensive).** `_default_field_arg` maps `@default(no)`→`default=False` and
    `@default(yes)`→`default=True` **only when the field type is `Boolean`** (a bareword default on a
    non-boolean field remains a string enum member). This protects hand-authored schemas.
  - **FR-F13b (emitter, canonical).** The manifest→Prisma emitter emits `@default(false)` /
    `@default(true)` (not `@default(no|yes)`) for `yes/no … default:` boolean fields, so the schema
    itself is canonical.
- **FR-F3b.** The backend generator must emit unique constraints the parser already recognizes.
  - **FR-F3b-i.** A field-level `@unique` (`PrismaField.is_unique`) emits `unique=True` in that
    column's `Field(...)`.
  - **FR-F3b-ii.** A model-level `@@unique([a, b])` emits a `__table_args__ = (UniqueConstraint("a",
    "b"),)` on the table class (composite uniqueness). Single-column `@@unique([a])` is acceptable as
    either form.
  - **FR-F3b-iii.** Emission must not duplicate a constraint already implied by `@id`/`@@id` (PK is
    inherently unique).
- **FR-F1/F8.** Extraction must not silently truncate an in-table `choice of:` enum, and
  `kickoff check` must not report "docs conform" when it happened.
  - **FR-F1a (value-level sanity).** When a field's declared type is `choice of:` and extraction
    yields **exactly one** enum value, emit an extraction record/warning
    (`choice-of-single-value`) keyed to the entity.field — surfaced by `kickoff check`.
  - **FR-F1b (author guidance).** The FORMAT worked example shows `choice of:` **inside a table**
    with `\|`-escaped pipes (today the sample is shown outside a table, so it doesn't warn authors).
  - **FR-F1c (optional detection).** Where feasible, detect a raw table cell containing `choice of:`
    with unescaped `|` and warn/auto-unescape at parse time.

### P1 — crash → clear error

- **FR-F2.** A `board` view whose `order` is empty must not crash with `IndexError`.
  - **FR-F2a (guaranteed).** Validate at parse/spec time (`parse_views` / `ViewSpec`
    construction) that a `board` view has a non-empty `order`; if absent, raise
    `ValueError("board '<name>': group_by '<field>' requires an Order:")`. Also guard the test
    emitter (`renderers.py:1550`) so no `board` spec can reach it with empty `order`.
  - **FR-F2b (optional enhancement).** If `known_enums` is threaded into `parse_views`, derive
    `order` from the group-by enum's declared values automatically (removing the need for an explicit
    `Order:`). Deferred unless cheap.
- **FR-H3.** `_render_workspace` on a non-polymorphic root must raise
  `ValueError("workspace '<name>': requires a polymorphic relation (of/type_field/id_field/type_map); root '<root>' has none")`
  instead of `assert p is not None`. (Also decide DX per NR: `workspace` is polymorphic-only today —
  documented, not renamed, in this pass.)

### P2 — contract honesty / modeling

- **FR-F3.** `has one <X>` must model one-to-one, not one-to-many.
  - **FR-F3-i.** The relationship grammar (`entities.py:409`) must carry the verb's cardinality
    (`has one` = singular) distinctly from `has many`.
  - **FR-F3-ii.** The Prisma emitter emits a singular relation (`X?`) **and** `@unique` on the child
    FK for `has one` (which, with FR-F3b, becomes a real DB constraint).
  - **FR-F3-iii.** If full support is not landed this pass, `kickoff check` must **flag `has one` as
    unsupported** rather than silently emit has-many (no silent-wrong).
- **FR-H4.** A VIPP `capture` of a `<Entity>.<field>` value-path must have a **consistent** story
  between negotiate and apply.
  - **FR-H4a.** At **negotiate** (`evaluate.py`), a `capture` whose value-path has **no writable
    target** in the kickoff manifest must be adjudicated **ACCEPT-but-inert** (or carry an explicit
    `value_path_not_allowed`/`not-mapped` qualifier), so the disposition report does not imply a
    write the floor will refuse.
  - **FR-H4b.** The apply summary must not read as a silent partial (`wrote 1/2`) for a proposal that
    was *never* actionable; inert proposals are reported as inert, not as failed writes.
  - **FR-H4c (non-goal clarifier).** Widening the apply-floor allow-list to accept `<Entity>.<field>`
    paths is **explicitly rejected** (different namespace, no write target) — see NR-4.
- **FR-H5.** Authored `observability.yaml` must either be a **first-class input** or **documented as
  advisory-only** — never silently dropped.
  - **FR-H5a (SDK-side, in-repo).** `scripts/generate_observability_artifacts.py` gains an optional
    `--observability-yaml` flag, threaded into both `generate_observability_artifacts(...)` call
    sites (the function already accepts `observability_yaml_path`).
  - **FR-H5b (cross-repo, tracked).** cap-dev-pipe Stage 7
    (`~/Documents/dev/cap-dev-pipe/pipeline/stages/observability.py`) threads the path through
    `run_observability()` → `generate(...)`. Tracked as a **separate cap-dev-pipe change**.
  - **FR-H5c (docs).** `NEXT_STEPS` / `O11Y_CORE_BUILD_RUNBOOK` state the real contract (manifest vs
    observability.yaml) so authored intent cannot be dropped without warning.

---

## 3. Non-Requirements

- **NR-1.** No fix to the two **already-resolved** items: H1 (wireframe `KeyError 'api'`, fixed at
  `wireframe/plan.py:1138`) and H2 (MCP `questionary` ModuleNotFoundError, fixed via lazy import at
  `concierge_view.py:525,531`). Confirmed fixed this session.
- **NR-2.** Not addressing the **P3 DX** portal findings here (F4 shared named enums, F5
  relationship/FK name hints, F6 `--with-manifests` app.yaml placement, F7 `--pages` stubbing, F9
  `--gate` compile-only docs, F10 workbook UID default, F11 deployed-mode note). Logged for a later
  DX pass.
- **NR-3.** Not renaming the `workspace` view archetype (H3 DX half) — only making it flag-don't-crash
  and documenting that it is polymorphic-only.
- **NR-4.** Not widening the kickoff apply-floor allow-list to entity-field value-paths (FR-H4c).
- **NR-5.** Not building auto-derivation of board order from enums (FR-F2b) unless it falls out cheaply
  from threading `known_enums`.
- **NR-6.** Not authoring real observability thresholds/content (bucket 4) — H5 is a wiring/honesty
  fix only.

---

## 4. Open Questions

- **OQ-4 → RESOLVED (full support).** Land full `has one` one-to-one support: thread verb cardinality
  end-to-end (singular relation + `@unique` on child FK). Will pass through CRP before implementing
  (batched with H4, F1/F8). FR-F3-iii (flag-only) is the fallback if CRP surfaces a blocker.
- **OQ-5.** For FR-H4, is **ACCEPT-but-inert** the right disposition, or should such captures be
  `OMIT` with a reason at negotiate? (Affects how the VIPP disposition report reads.)
- **OQ-6.** For FR-H5, do we treat `observability.yaml` as authoritative-when-present (override
  manifest) or additive (merge)? Merge semantics need a precedence rule.
- **OQ-7.** F1/F8: is the value-level `choice-of-single-value` signal a **hard** conformance failure
  (`kickoff check --strict` exits non-zero) or a **warning**? Hard = safer (matches "silent data
  loss"), but may false-positive on a legitimately single-value closed vocabulary.

---

*v0.3 — Post lessons-learned hardening. Applied 4 SDK lessons (regression base-repro, SQLModel
MetaData teardown, golden-snapshot text-compare, phantom-reference audit). v0.2 reframed 3
requirements (H4, F2, H5), promoted 2 to belt-and-suspenders (F13, F3+F3b), demoted 1 to optional
(F2b), raised 4 open questions. Ready for CRP review.*
