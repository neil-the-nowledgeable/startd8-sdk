# Client-Logged Friction Fixes — Requirements

**Version:** 0.4 (Post-CRP R1 triage)
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
- **FR-0c (red-on-main exemption for un-testable sub-reqs).** *(R1-F8)* FR-0's "fails on `main`"
  mandate applies to executable behavior only. **Docs-only** sub-requirements (FR-F1b, FR-H5c) and
  **optional heuristics** (FR-F1c, FR-F2b) that cannot produce a failing assertion are **exempt** —
  verified by inspection, not a red-on-main test. The verification gate must not read as blocking
  them (which would be its own silent waiver).

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
  - **FR-F1d (advisory tier — PREREQUISITE, R1-F3/R1-S2).** The extraction record model has no
    warning severity today: `Status` (`manifest_extraction/models.py:19-22`) is only
    `EXTRACTED | NOT_EXTRACTED | DEFAULTED`, and `cli_kickoff.py:_is_conformance_failure` gates
    `--strict` on `NOT_EXTRACTED` minus the `generator-gap` marker. So `choice-of-single-value` has
    **no home** — `NOT_EXTRACTED` always hard-fails (killing OQ-7's warn option); `EXTRACTED` stays
    false-green (the original bug). **Before FR-F1a can land, introduce an advisory/warning tier** (a
    new severity, or a reserved `reason` marker analogous to `generator-gap`) and define how
    `_is_conformance_failure` treats it under `--strict` vs default. This is a blocking prerequisite,
    not a detail.
  - **FR-F1e (truncation-vs-genuine disambiguator, R1-F4).** A `choice of:` that truncated to one
    value must be distinguishable from a genuinely single-member vocabulary. The signal lives in the
    **raw cell text** — a cell that *contained* `|`-separated tokens but extracted to one value (a
    stripped pipe) is evidence of loss; a cell whose raw source had one token is not.
    `entities.py:236` currently discards this after `split("|")` — **preserve it** so a hard-fail
    fires only on evidence of truncation (making OQ-7's "hard" option safe).
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
  - **FR-F3-iii (DEFAULT landing, R1-F2/R1-S4).** `kickoff check` must **flag `has one` as
    unsupported** rather than silently emit has-many (no silent-wrong). This flag-don't-emit floor is
    now the **default first landing**; full support (FR-F3-i/ii) is an explicit incremental opt-in
    once the design forks below are resolved. (Supersedes OQ-4's earlier "full support" resolution.)
  - **FR-F3-iv (migration safety — PREREQUISITE for full support, R1-F1/R1-S3).** Adding `@unique`
    to a child FK (FR-F3-ii) is **not free on populated tables**: a schema edited from `has many`
    to `has one` over data with duplicate parent references fails at **constraint-creation / migration
    time** — silent-wrong converts to a hard migration failure the spec previously did not
    acknowledge. Before emitting `@unique` for a `has one`, require a stated precondition (child table
    empty, or a documented dedup/validation step) and specify the failure mode: **schema-gen warns;
    migration is the enforcement point**. The full-support path must not assume `@unique` is safe.
    Unresolved design forks gating full support: self-relations, optional-vs-required one-to-one, and
    existing `has many` datasets.
- **FR-H4.** A VIPP `capture` of a `<Entity>.<field>` value-path must have a **consistent** story
  between negotiate and apply.
  - **FR-H4a.** At **negotiate** (`evaluate.py`), a `capture` whose value-path has **no writable
    target** in the kickoff manifest must be adjudicated **ACCEPT-but-inert**, carrying the
    **existing typed reason code** `CaptureCode.VALUE_PATH_NOT_ALLOWED` (R1-F6) — **not** a new
    parallel string like `not-mapped-to-kickoff-inputs` (two names for one condition re-creates the
    negotiate/apply divergence this FR closes), so the disposition report does not imply a write the
    floor will refuse.
    - **Locus note (R1-F5/R1-S1 — reviewer correction REJECTED, nuance kept).** The VIPP apply path
      is `vipp/apply.py:36` → `apply_proposal` in `kickoff_experience/proposals.py` → the refusal at
      `proposals.py:309-310` (`ProposalOutcome(..., CaptureCode.VALUE_PATH_NOT_ALLOWED)`). That is the
      correct locus this FR cites. `kickoff_experience/capture.py:285-296` raises the **same code**
      via a **different** path (the direct-capture CLI, `CaptureError`) — a parallel floor, not the
      VIPP one. The FR-0 red-on-main test therefore targets the VIPP negotiate→apply path, not
      `capture.py`.
  - **FR-H4b.** The apply summary must not read as a silent partial (`wrote 1/2`) for a proposal that
    was *never* actionable; inert proposals are reported as inert, not as failed writes. **Preview
    parity (R1-F9/R1-S8):** the side-effect-free preview (`vipp/apply.py` `would_apply` /
    `content_hash`) must **also** exclude an inert proposal — else preview over-promises exactly the
    write apply makes honest.
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

- **OQ-4 → SUPERSEDED by CRP R1 (flag-only default, full support incremental).** The v0.3 "full
  support" resolution was over-eager: CRP surfaced the FR-F3-iv migration hazard plus unresolved
  forks (self-relations, optional-vs-required, existing `has many` data). New position: **land
  FR-F3-iii (flag-as-unsupported) first**; full one-to-one support is an incremental opt-in gated on
  FR-F3-iv + the forks. (R1-F2/R1-S4.)
- **OQ-5.** For FR-H4, is **ACCEPT-but-inert** the right disposition, or should such captures be
  `OMIT` with a reason at negotiate? *(Leaning ACCEPT-but-inert per R1; either way it carries the
  existing `CaptureCode.VALUE_PATH_NOT_ALLOWED`, FR-H4a.)*
- **OQ-6 → RESOLVED (additive/opt-in — read from the code, 2026-07-09).** Read the real function
  `startd8.observability.artifact_generator.generate_observability_artifacts` (`artifact_generator.py:417-426`;
  the `scripts/` file only wraps it). Line 516 states the contract: **"additive + opt-in: an absent
  `observability_yaml_path` ⇒ no new artifact"** — present ⇒ EXTRA domain alert + dashboard artifacts
  from `alerting.metric_thresholds` / `service_levels` (via `from_observability_yaml`); it **never
  overrides the manifest**. So there is **no override-vs-merge decision and no silent-manifest-drop
  risk**; the only gap was the CLI never exposed/threaded the flag (now fixed, FR-H5a — **IMPLEMENTED**
  on `impl/client-friction-p2`). *(The earlier claim that the `scripts/` file itself had the param was
  a misread — the param is on the imported function.)*
- **OQ-7 → blocked on FR-F1d.** The hard-vs-warn question is **unanswerable until the record model
  gains an advisory tier** (FR-F1d). Once it exists, lean **warn by default, `--strict` promotes to
  hard**, and use FR-F1e's raw-cell evidence so hard only fires on actual truncation. (R1-F3/R1-S2.)

---

*v0.4 — Post-CRP R1 triage. Accepted 8 of 9 requirements suggestions: added FR-0c (red-on-main
exemption), FR-F1d (advisory-tier prerequisite — blocks OQ-7), FR-F1e (truncation disambiguator),
FR-F3-iv (migration safety — gates full has-one support), demoted OQ-4 to flag-only-default; refined
FR-H4a (reuse CaptureCode), FR-H4b (preview parity), OQ-6 (read-code-first). Rejected R1-F5 (H4 locus
"correction" was itself a misread — verified `proposals.py:309-310` IS the VIPP path). Dispositions
in Appendix A/B. v0.3 applied 4 SDK lessons; v0.2 reframed H4/F2/H5.*

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
| R1-F1 | FR-F3-iv migration-safety precondition for `@unique` on `has one` child FK | CRP R1 (opus-4-8) | Added FR-F3-iv; gates full has-one support on empty-table/dedup precondition | 2026-07-09 |
| R1-F2 | Make flag-only (FR-F3-iii) the default landing, full support opt-in | CRP R1 | Rewrote FR-F3-iii as DEFAULT; superseded OQ-4 | 2026-07-09 |
| R1-F3 | Add advisory/warning tier — record model has none (`Status` = extracted/not_extracted/defaulted) | CRP R1 | Added FR-F1d as blocking prerequisite; OQ-7 now gated on it | 2026-07-09 |
| R1-F4 | Truncation-vs-genuine disambiguator via preserved raw cell text | CRP R1 | Added FR-F1e (preserve stripped-pipe evidence, `entities.py:236`) | 2026-07-09 |
| R1-F6 | Reuse `CaptureCode.VALUE_PATH_NOT_ALLOWED`, don't invent a new string | CRP R1 | FR-H4a now mandates the existing typed code | 2026-07-09 |
| R1-F7 | Resolve OQ-6 from the code (function already has a precedence behavior) | CRP R1 | OQ-6 refined to read-code-before-documenting | 2026-07-09 |
| R1-F8 | FR-0 exemption for docs-only / optional sub-reqs (can't fail red-on-main) | CRP R1 | Added FR-0c | 2026-07-09 |
| R1-F9 | Assert preview (`would_apply`) parity for inert proposals | CRP R1 | FR-H4b now requires preview to exclude inert | 2026-07-09 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-F5 | "FR-H4 apply-refusal locus is wrong — it's `capture.py:44`, not `proposals.py:308-311`" | CRP R1 (opus-4-8) | **Misread.** Verified: `vipp/apply.py:36` imports `apply_proposal` from `kickoff_experience.proposals`; the VIPP-path refusal IS `proposals.py:309-310` (`ProposalOutcome(..., VALUE_PATH_NOT_ALLOWED)`). `capture.py:285-296` raises the same code on a *different* (direct-capture CLI) path; `capture.py:44` is a comment. My cited locus stands. Kept the useful **dual-locus nuance** as a note under FR-H4a. | 2026-07-09 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: Claude Opus 4.8 (claude-opus-4-8-1m)
- **Date**: 2026-07-09 UTC
- **Scope**: Requirements review weighted per CRP_FOCUS on FR-F3 (§2/OQ-4), FR-F1/F8 (§2/OQ-7), FR-H4 (§3/OQ-5); also OQ-6 and cross-cutting FR-0. Source loci re-verified against current `src/` this session.

**Focus-file asks — answered (top of block):**

*Ask 1 — FR-F3 `has one` full one-to-one support (OQ-4):*
- **Summary answer:** Full support is right *only if* it lands behind FR-F3-iii as the default fallback; the `@unique`-on-existing-many-row hazard is real and must be gated by a data-precondition check, not assumed safe.
- **Rationale:** Verified `entities.py:412` — the branch is literally `verb in ("has many", "has one")` and both append the *same* `ExtractionRecord` (`value=f"{obj}.{_lower_camel(subj)}Id"`, line ~419-421), so cardinality is genuinely dropped at extraction, not just at emit. Adding `@unique` to a child FK that already holds duplicate parent references (a pre-existing `has many` dataset an author edits to `has one`) makes the migration fail at constraint-creation time on populated DBs — silent-wrong converts to a hard migration failure, which FR-F3 does not currently acknowledge.
- **Assumptions / conditions:** That some downstream schemas already say `has many` and hold multi-row data (stated as a press-on item in the focus file); that F3b lands first so `@unique` actually reaches `tables.py`.
- **Suggested improvements:** Add FR-F3-iv (migration-safety precondition) + make FR-F3-iii the *default* landing with full support opt-in — see R1-F1, R1-F2.

*Ask 2 — FR-F1/F8 in-table `choice of:` truncation + kickoff-check sanity (OQ-7):*
- **Summary answer:** OQ-7 as posed is unanswerable because the record model can't express "warning" today — resolve the model gap first; then default to **warn**, with `--strict` promoting to hard.
- **Rationale:** `manifest_extraction/models.py:19-22` — `Status` is only `EXTRACTED | NOT_EXTRACTED | DEFAULTED`; there is no severity axis. `cli_kickoff.py:_is_conformance_failure` gates `--strict` on `NOT_EXTRACTED` minus the `generator-gap` marker. A `choice-of-single-value` signal therefore has **no home**: mark it `NOT_EXTRACTED` and it hard-fails unconditionally (defeating OQ-7's "warning" option); mark it `EXTRACTED` and `kickoff check` stays false-green (the original bug). The spec must add a warning/advisory tier or a marker convention before OQ-7 can be decided.
- **Assumptions / conditions:** none — this is verifiable by reading the two files.
- **Suggested improvements:** R1-F3 (add advisory tier), R1-F4 (truncation-vs-genuine disambiguator).

*Ask 3 — FR-H4 VIPP disposition honesty (OQ-5):*
- **Summary answer:** ACCEPT-but-inert with a qualifier reads more honestly than OMIT, but FR-H4's cited apply-refusal locus is **wrong** and must be corrected before any test can be written.
- **Rationale:** REQUIREMENTS §1 row H4 and Step 7 cite `proposals.py:308-311` for the refusal, but the actual refusal is `CaptureError(CaptureCode.VALUE_PATH_NOT_ALLOWED)` from `kickoff_experience/proposals.py` (surfaced via `vipp/apply.py:36` importing `apply_proposal`); the code lives in `kickoff_experience/capture.py:44`, not `vipp/proposals.py`. FR-0 mandates verified loci with exact `file:line`; this one fails that bar and would make the FR-0 red-on-main test target the wrong file.
- **Assumptions / conditions:** that `CaptureCode.VALUE_PATH_NOT_ALLOWED` is the code the apply floor raises for entity-field paths (confirmed present at `capture.py:44`).
- **Suggested improvements:** R1-F5 (fix the locus + name the real `CaptureCode`), R1-F6 (make the inert qualifier reuse the existing `CaptureCode` vocabulary rather than inventing a new string).

**Numbered suggestions (requirements):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | Add **FR-F3-iv (migration safety)**: before emitting `@unique` on a child FK for a `has one` that was previously `has many`, require a stated precondition — either the child table is empty, or a data-dedup/validation step is documented — and specify the failure mode (schema-gen warns; migration is the enforcement point). | FR-F3-ii adds `@unique` unconditionally; on an existing populated `has many` table this turns silent-wrong into a hard migration failure. The spec never states what happens to existing multi-row data. | New sub-bullet under FR-F3 | A golden with a `has many`→`has one` edit over seed data asserts a named pre-migration warning, not an opaque constraint-violation traceback. |
| R1-F2 | Risks | high | Make **FR-F3-iii the default landing** and full support (F3-i/ii) an explicit opt-in for this pass, rather than "fallback if CRP surfaces a blocker" (OQ-4). | OQ-4 says "RESOLVED (full support)" but the press-on items (self-relations, optional-vs-required, existing `has many` data) are unresolved design forks. Flag-don't-emit is the guaranteed-honest floor; full support can land incrementally without risking silent one-to-many on ambiguous inputs. | §4 OQ-4 + FR-F3 ordering | Verify `kickoff check` emits `has-one-unsupported` for any `has one` not covered by the landed full-support cases. |
| R1-F3 | Validation | high | FR-F1a assumes a record can be "a warning surfaced by `kickoff check`", but `Status` (`models.py:19-22`) has no warning tier. Add an explicit requirement to introduce an **advisory/warning severity** (or a reserved `reason` marker analogous to `generator-gap`) and define how `_is_conformance_failure` treats it under `--strict` vs default. | Without this, `choice-of-single-value` is forced into `NOT_EXTRACTED` (always hard-fails, contradicting OQ-7's warning option) or `EXTRACTED` (stays false-green). OQ-7 cannot be answered until the model supports "warning". | New FR under P0 F1/F8, referenced by OQ-7 | Unit test: a single-value `choice of:` yields a record classified as advisory; default `kickoff check` exit 0 with visible warning, `--strict` exit non-zero. |
| R1-F4 | Data | medium | For OQ-7, add an acceptance criterion for the **truncation-vs-genuine-single-member disambiguator**: a `choice of:` cell that *contained* `\|`-separated tokens but extracted to one value (evidence of a split at an unescaped pipe) is treated differently from a cell whose raw source had exactly one token. | The focus file asks "what disambiguates a truncation from a genuine single-value enum?" — the answer is in the *raw cell text* (presence of a stripped `|`), which `entities.py:236` discards after `split("|")`. Preserving that signal makes hard-fail safe (only fires on evidence of loss). | FR-F1a / FR-F1c | Test: `choice of: a\|b\|c` truncated → flagged; `choice of: single` → not flagged. |
| R1-F5 | Interfaces | high | Correct the **FR-H4 apply-refusal locus**: §1 table and OQ-5 cite `proposals.py:308-311`, but the refusal is `CaptureError(CaptureCode.VALUE_PATH_NOT_ALLOWED)` defined at `kickoff_experience/capture.py:44` and enforced through `kickoff_experience/proposals.py` (imported by `vipp/apply.py:36`), not `vipp/proposals.py`. | FR-0 requires verified loci; a wrong `file:line` points the mandatory red-on-main test at a file that never raises, so the test would be vacuous. | §1 table row H4 + §4 OQ-5 | Grep confirms `value_path_not_allowed` exists only in `kickoff_experience/capture.py`, not `vipp/proposals.py`. |
| R1-F6 | Interfaces | medium | In FR-H4a, specify that the inert qualifier **reuses the existing `CaptureCode` vocabulary** (`VALUE_PATH_NOT_ALLOWED`) rather than inventing a parallel `not-mapped-to-kickoff-inputs` string. | The requirement offers two candidate reason strings; one already exists as a typed stable code (`capture.py:44`, "R4-F4 stable typed reason codes"). Two names for one condition re-creates the negotiate/apply divergence FR-H4 exists to close. | FR-H4a | Assert the negotiate disposition's qualifier `== CaptureCode.VALUE_PATH_NOT_ALLOWED`. |
| R1-F7 | Ops | medium | Resolve **OQ-6** in the requirements (not just the plan/docs): state whether authored `observability.yaml` overrides or merges with the manifest, because `generate_observability_artifacts(observability_yaml_path=...)` already has *a* behavior on disk today — the spec should assert what it is and whether it's the intended contract, else FR-H5 wires a param whose semantics are undefined. | FR-H5a threads a path into a function that already accepts it; if that function's precedence is "override" but authors expect "merge", H5 ships a *new* silent-drop (manifest values lost). OQ-6 is currently deferred to docs (FR-H5c) but it's a contract decision. | §4 OQ-6 + FR-H5 | Read `generate_observability_artifacts` body; assert observed precedence matches the documented contract in a test. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Validation | medium | FR-0 says every fix ships a test that "fails on `main`". For FR-F1c (auto-unescape at parse time) and FR-H5c (docs), there is **no executable red-on-main assertion possible** — a doc change and an optional heuristic can't fail red. State FR-0's exemption for docs-only/optional sub-requirements explicitly so the verification gate isn't interpreted as blocking them. | The verification gate checkbox "Each step's regression test fails on `main`" is unsatisfiable for FR-H5c/FR-F1b (pure docs) and ambiguous for optional FR-F1c/FR-F2b. Unstated, it either blocks merge or gets silently waived (the exact silent behavior this doc opposes). | FR-0 + §Verification gate (plan) | N/A — spec-clarity criterion; verify the gate text names the exemption. |
| R1-F9 | Security | low | FR-H4b guards against a `wrote 1/2` silent-partial in the apply summary, but does not state what the **preview** (`apply.py:90` `apply_dispositions` preview / `would_apply`) reports for an inert proposal. If preview shows it as would-write while apply reports inert, the two disagree. | The VIPP apply path has a side-effect-free preview (`would_apply`, `content_hash` at `apply.py:94-95`); an inert-but-accepted proposal must be excluded from `would_apply` too, or preview over-promises exactly what FR-H4 fixes at apply. | FR-H4b | Test: an inert `capture` is absent from `would_apply` and its `content_hash` is unchanged. |

**Endorsements / Disagreements:** none — this is round R1; Appendices A/B/C carry no prior untriaged items.
