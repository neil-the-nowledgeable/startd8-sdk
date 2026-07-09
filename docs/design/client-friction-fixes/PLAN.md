# Client-Logged Friction Fixes — Implementation Plan

**Version:** 1.1 (post-CRP R1 triage, paired with REQUIREMENTS v0.4)
**Date:** 2026-07-09
**Branch:** `fix/client-friction-triage-p0p2`

> **v1.1 changes (CRP R1):** Step 1b locus pinned (`prisma_emitter.py:233`); Step 3 restructured to
> flag-only default + full-support gated on a new migration-safety substep (3c) + MetaData teardown
> note; Step 6 gained a 6a-0 advisory-tier prerequisite + truncation disambiguator; Step 7 keeps its
> (verified-correct) VIPP refusal locus, adds preview-parity assertion; Step 8 gained an 8a-0
> read-precedence-first step; Step 4 gained a present-but-empty sentinel test. R1-S1 rejected
> (locus misread). Dispositions in Appendix A/B.

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

**1b. Emitter (canonical).** `src/startd8/manifest_extraction/prisma_emitter.py:232-243` — the
`@default` emission. At **line 233**, `dv = _quote_string_default(f.default) if f.prisma_type ==
"String" else f.default` passes a Boolean field's bareword default through verbatim → `Boolean
@default(no)`. Fix: when `f.prisma_type == "Boolean"` and `f.default in ("yes","no")`, emit
`false`/`true`. *(Locus pinned per CRP R1 coverage matrix — was previously unspecified.)*

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

## Step 3 — FR-F3: `has one` one-to-one (OQ-4 → flag-only default)

**Landing decision (revised by CRP R1, R1-S4/R1-F2).** OQ-4's earlier "full support" resolution is
superseded. **Default first landing = FR-F3-iii (flag-as-unsupported)**; full support is an
incremental opt-in gated on the migration-safety substep (3c) and the unresolved forks
(self-relations, optional-vs-required, existing `has many` data).

**3a. Flag-only (DEFAULT).** `src/startd8/manifest_extraction/entities.py:409` — the branch is
`elif verb in ("has many", "has one"):` (both append the *same* FK `ExtractionRecord`, ~419-421, so
cardinality is dropped at extraction). Split `has one` out and emit a `kickoff check`
`has-one-unsupported` signal instead of a silent has-many. Small, honest, no schema risk.

**3b. Full-support edits (INCREMENTAL opt-in, gated on 3c).**
- `entities.py:409` — carry a `cardinality="one"` signal distinctly from `has many`.
- `src/startd8/manifest_extraction/prisma_emitter.py` — for `cardinality="one"`, emit the parent side
  singular (`X?`) **and** `@unique` on the child FK scalar. With Step 2 (FR-F3b) this becomes a real
  DB constraint.

**3c. Migration-safety precondition (FR-F3-iv, R1-S3/R1-F1) — REQUIRED before 3b ships.** Adding
`@unique` to a child FK is **not free on populated tables**: a schema edited from `has many` to
`has one` over data with duplicate parent refs fails at **constraint-creation / migration** time
(silent-wrong → hard failure). Emit a **schema-gen warning** stating the precondition (child table
empty, or a documented dedup step); migration is the enforcement point. Do not assume `@unique` is
safe.

**Regression tests:**
- *3a:* `an Assignment has one Review` on `main` emits `reviews Review[]`; with 3a, `kickoff check`
  emits `has-one-unsupported` (no silent has-many).
- *3b:* extraction golden → `review Review?` (singular) + `@unique` on `Review.assignmentId`;
  end-to-end the generated `tables.py` has `unique=True` on the FK (depends on Step 2).
- *3c:* a `has many`→`has one` edit over seed data with duplicate FKs surfaces the **named warning**,
  not an opaque constraint-violation traceback.
- **Lesson note (Testing #9, R1-S7):** the 3b end-to-end test instantiates generated `tables.py`, so
  it hits the same process-global SQLModel `MetaData` collision as Step 2 — drop owned tables at
  setup **and** teardown (scoped `md.remove`, not `md.clear`).

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
**Two-sentinel case (R1-S6):** assert BOTH `order:` omitted AND `order:` present-but-empty raise the
named ValueError — the guard (`entry.get("order") or []`) and the emitter guard (`not v.order`)
must agree on which sentinel means "absent". *(As-implemented in PR #175 both are covered; this adds
the explicit present-but-empty case.)*

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

**6a-0. Advisory tier (PREREQUISITE, R1-S2/R1-F3) — do FIRST.** The record model has no warning
severity: `Status` (`manifest_extraction/models.py:19-22`) is only `EXTRACTED | NOT_EXTRACTED |
DEFAULTED`, and `_is_conformance_failure` (`cli_kickoff.py:~48-56`) gates `--strict` on
`NOT_EXTRACTED` minus the `generator-gap` marker. So `choice-of-single-value` has no home today.
**Introduce an advisory tier** (a new severity, or a reserved `reason` marker mirroring
`generator-gap`) and define its `--strict`-vs-default treatment BEFORE wiring 6a/6b. Without this,
OQ-7 is unanswerable (see FR-F1d).

**6a. Extraction signal.** `src/startd8/manifest_extraction/entities.py:237` (after `enum_values`
computed, before the field record is appended, ~237-253): when the field is `choice of:` and
`len(enum_values) == 1`, emit the advisory record `choice-of-single-value` keyed to `Entity.field`.
**Disambiguator (FR-F1e/R1-F4):** preserve the raw cell text (a stripped `|` = evidence of
truncation) — `entities.py:236` currently discards it after `split("|")` — so the signal fires on
loss, not on a genuine single-member vocabulary.

**6b. kickoff check surfacing.** `src/startd8/cli_kickoff.py` — `_is_conformance_failure` treats the
advisory record per 6a-0: **warn by default (exit 0, visible), `--strict` promotes to hard** (OQ-7
resolution, once 6a-0 lands).

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
writable target** in the kickoff manifest, must be adjudicated **ACCEPT-but-inert** — carrying the
**existing typed code** `CaptureCode.VALUE_PATH_NOT_ALLOWED` (R1-F6; not a new parallel string). (Per
FR-H4c / NR-4, do **not** touch `proposals.py`/`manifest.py` to widen the floor.)

**Refusal-locus note (R1-S1/R1-F5 — reviewer correction REJECTED, verified).** The VIPP apply path is
`vipp/apply.py:36` → `apply_proposal` in `kickoff_experience/proposals.py` → the refusal at
`proposals.py:309-310` (`ProposalOutcome(..., CaptureCode.VALUE_PATH_NOT_ALLOWED)`). **That is the
correct locus.** CRP R1 claimed it was `capture.py:44`; verified false — `capture.py:285-296` raises
the same code on the *different* direct-capture CLI path (`CaptureError`), and `capture.py:44` is a
comment. The FR-0 red-on-main test targets the VIPP negotiate→apply path, which is correct.

Decide the exact disposition per **OQ-5** (ACCEPT-but-inert vs OMIT-with-reason).

**Regression test:** `tests/unit/vipp/test_evaluate.py` — a `capture` of `Chore.name` (a real field)
adjudicates to the inert/qualified disposition, and a full negotiate→apply run reports it as **inert,
not `wrote 1/2`**. **Preview parity (R1-S8/R1-F9):** also assert the inert proposal is **absent from
`would_apply`** and its `content_hash` is unchanged (`vipp/apply.py` preview), so preview and apply
agree. On `main`, assert negotiate returns a plain ACCEPT[VALIDATED] that apply then refuses (the
dishonest split).

---

## Step 8 — FR-H5: observability.yaml wiring

**8a-0. Read the current precedence FIRST (R1-S5/R1-F7).** `generate_observability_artifacts`
(`scripts/generate_observability_artifacts.py:426`) already **accepts** `observability_yaml_path` —
read its body to record what it does *today* when the path is passed (override manifest? merge? and
with what precedence?). Decide OQ-6 from that observed behavior, not by inventing a rule 8c then
documents. If today's behavior is "override" but authors expect "merge", threading the flag (8a) ships
a **new silent manifest-drop** — the exact failure H5 exists to prevent.

**8a. SDK-side (in-repo).** `scripts/generate_observability_artifacts.py`:
- Add `--observability-yaml` argparse flag (optional, mirror `--manifest` at line 64-68).
- Thread `observability_yaml_path=Path(args.observability_yaml) if args.observability_yaml else None`
  into both `generate_observability_artifacts(...)` call sites (~142, ~173).

**8b. Cross-repo (tracked separately, FR-H5b).** `~/Documents/dev/cap-dev-pipe/pipeline/stages/
observability.py:32-86` — add `observability_yaml_path` to `run_observability()` and pass it to
`generate(...)`. **This is the canonical cap-dev-pipe repo (symlinked)** — land as its own change
with its own branch/PR, not folded into this SDK PR.

**8c. Docs (FR-H5c).** Update `NEXT_STEPS` / `O11Y_CORE_BUILD_RUNBOOK` to state the real contract and
the precedence **observed in 8a-0** (not a rule chosen after the fact).

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
| R1-S2 | Advisory-tier prerequisite before wiring the choice-of signal | CRP R1 (opus-4-8) | Added Step 6a-0; OQ-7 gated on it | 2026-07-09 |
| R1-S3 | Migration-safety substep for `@unique` on `has one` child FK | CRP R1 | Added Step 3c; full support (3b) gated on it | 2026-07-09 |
| R1-S4 | Make Step 3 flag-only the default, full support opt-in | CRP R1 | Restructured Step 3 (3a default / 3b incremental) | 2026-07-09 |
| R1-S5 | Read function's current precedence before documenting OQ-6 | CRP R1 | Added Step 8a-0; 8c documents observed behavior | 2026-07-09 |
| R1-S6 | Test both omitted AND present-but-empty `order` sentinels | CRP R1 | Added two-sentinel case to Step 4 test | 2026-07-09 |
| R1-S7 | SQLModel MetaData teardown note applies to Step 3 e2e test too | CRP R1 | Added lesson note to Step 3 tests | 2026-07-09 |
| R1-S8 | Assert preview (`would_apply`) parity for inert VIPP proposal | CRP R1 | Added to Step 7 regression test | 2026-07-09 |
| (matrix) | Pin the FR-F13b emitter locus | CRP R1 coverage matrix | Step 1b pinned to `prisma_emitter.py:233` | 2026-07-09 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S1 | "Step 7 edit locus is wrong — refusal is `capture.py:44`, not `proposals.py:308-311`" | CRP R1 (opus-4-8) | **Misread (same as R1-F5).** Verified `vipp/apply.py:36` → `apply_proposal` in `kickoff_experience.proposals` → refusal at `proposals.py:309-310`. That IS the VIPP path and the correct locus. `capture.py:285-296` is a parallel floor on the direct-capture CLI path; `capture.py:44` is a comment. Kept the dual-locus nuance as a note in Step 7. | 2026-07-09 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: Claude Opus 4.8 (claude-opus-4-8-1m)
- **Date**: 2026-07-09 UTC
- **Scope**: Plan review weighted per CRP_FOCUS on Step 3 (FR-F3/OQ-4), Step 6 (FR-F1/F8/OQ-7), Step 7 (FR-H4/OQ-5); also Step 8/OQ-6 and cross-cutting FR-0 sequencing. Loci re-verified against current `src/` this session.

**Executive summary (top risks / gaps):**
- Step 7's edit target is misattributed — the apply refusal is in `kickoff_experience/capture.py`/`proposals.py` (via `vipp/apply.py:36`), **not** `vipp/evaluate.py` alone; the FR-0 red-on-main assertion in Step 7 as written won't reproduce the split.
- Step 6 assumes a "warning" record tier that the extraction model lacks (`Status` = extracted/not_extracted/defaulted only) — OQ-7 can't be implemented as sequenced without a model change first.
- Step 3 full-support adds `@unique` to a child FK with no migration-safety step for pre-existing multi-row `has many` data — a hard migration failure hazard, not covered.
- Sequencing puts F3 (Step 3) before its own open question (OQ-4) is resolved; the "recommended first landing" excludes it, so Step 3's position in the numbered sequence is misleading.
- Step 8's cross-repo half (FR-H5b) is correctly deferred, but Step 8c writes the OQ-6 precedence rule into docs *before* OQ-6 is decided — order inversion.

**Numbered suggestions (plan):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | Fix Step 7's edit locus: the ACCEPT-but-inert change is in `vipp/evaluate.py`, but the **refusal it must stay honest about** is `CaptureError(CaptureCode.VALUE_PATH_NOT_ALLOWED)` from `kickoff_experience/capture.py:44` (enforced via `kickoff_experience/proposals.py`, imported at `vipp/apply.py:36`). Step 7 currently says "do not touch `proposals.py`/`manifest.py`" citing `vipp/` — name the `kickoff_experience` module so the test targets the real floor. | Step 7 cites `proposals.py:308-311` (from REQUIREMENTS §1) which does not contain the refusal; the red-on-main test would assert against a file that never raises `value_path_not_allowed`. | Step 7 "Edit" + "Regression test" | Grep: `value_path_not_allowed` appears only under `kickoff_experience/`, confirming the correct floor module. |
| R1-S2 | Validation | high | Step 6a emits a `choice-of-single-value` "extraction record", but the record model has no warning severity (`manifest_extraction/models.py:19-22`: `EXTRACTED\|NOT_EXTRACTED\|DEFAULTED`). Add a Step 6a-0 that either introduces an advisory tier or a reserved `reason` marker (mirroring `generator-gap` at `cli_kickoff.py:48`) **before** wiring 6b. | As sequenced, 6b's `_is_conformance_failure` can only see `NOT_EXTRACTED`; a single-value record is either always-hard (kills OQ-7's warn option) or invisible (keeps the false-green). The model change is a prerequisite, not a detail. | Step 6, new 6a-0 before 6a | Unit test: advisory record → default `kickoff check` exit 0 + printed warning; `--strict` exit non-zero. |
| R1-S3 | Data | high | Add a **migration-safety sub-step to Step 3** (full-support path): when `@unique` is added to a child FK for `has one`, document/emit a precondition check for existing multi-row parent references; do not assume `@unique` is free on populated tables. | Step 3's full-support edits (`prisma_emitter.py`) add `@unique` unconditionally; on a schema migrated from `has many` with duplicate rows, the DB constraint creation fails at migration, not at gen — an unhandled hard failure the plan doesn't name. | Step 3 "Full-support edits" | Golden: `has many`→`has one` over seed data with duplicate FKs surfaces a named warning, not an opaque constraint error. |
| R1-S4 | Risks | medium | Reorder or annotate the sequence so **Step 3 is explicitly gated/optional**: the sequencing rationale lists F3b→F3, but the "Recommended first landing" (Steps 1,2,4,5) excludes Step 3, and OQ-4's press-on items are unresolved. Mark Step 3 as "land FR-F3-iii (flag-only) in first pass; full support batched after OQ-4 forks resolved." | Two parts of the plan disagree on when Step 3 lands; a reader following the numbered order would attempt full `has one` before the migration-safety and self-relation forks are decided. | §Sequencing rationale + Step 3 header | N/A — sequencing clarity; verify Step 3 header states the gate. |
| R1-S5 | Ops | medium | Step 8c writes the OQ-6 precedence rule into `NEXT_STEPS`/`O11Y_CORE_BUILD_RUNBOOK`, but OQ-6 (override vs merge) is **undecided**. Add a Step 8a-precondition: read `generate_observability_artifacts` (line 426) and record its *current* precedence, so the doc states the real shipped behavior rather than a rule chosen after the fact. | The function already has a behavior when `observability_yaml_path` is passed; if it's "override" and authors expect "merge", threading the flag (8a) introduces a new silent manifest-drop. Decide OQ-6 from the code before documenting it. | Step 8a / 8c | Test asserting observed precedence == documented precedence. |
| R1-S6 | Validation | medium | Add a `board` **empty-string-vs-absent** case to Step 4's regression test: FR-F2a guards "empty `order`", but `parse_views` (order defaulted at line 447) may default `order` to `[]` vs leave it `None`. The guard and the test must agree on which sentinel means "absent". | An off-by-sentinel (guard checks `is None`, loader defaults `[]`) would make the guard silently not fire — reintroducing the `IndexError` the step fixes. | Step 4a / test | Two tests: `order:` omitted and `order:` present-but-empty both raise the named `ValueError`. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Validation | medium | Step 2's SQLModel `MetaData` teardown note (Testing #9) applies to Step 3's end-to-end test too — Step 3's regression test instantiates generated `tables.py` to assert `unique=True` on the FK, so it hits the same process-global `MetaData` collision. Add the drop-owned-tables setup/teardown note to Step 3, not just Step 2. | The lesson is attached only to Step 2, but any test that imports generated table classes shares the global metadata; Step 3's e2e assertion does. Omitting it risks the flaky/false-green the lesson exists to prevent. | Step 3 "Regression test" | Run Step 2 and Step 3 table tests in one session; assert no cross-test metadata collision. |
| R1-S8 | Interfaces | low | Step 7's regression test asserts a full `negotiate→apply` run reports "inert, not `wrote 1/2`", but does not assert the **preview** (`vipp/apply.py:90` `apply_dispositions` preview / `would_apply`) excludes the inert proposal. Add that assertion so preview and apply agree. | An inert-but-ACCEPTed proposal left in `would_apply` (apply.py:94) makes the side-effect-free preview over-promise the same write FR-H4 makes honest at apply. | Step 7 "Regression test" | Assert inert `capture` absent from `would_apply`; `content_hash` unchanged. |

**Endorsements / Disagreements:** none — round R1; no prior untriaged suggestions exist in Appendix C.

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each REQUIREMENTS FR to the PLAN step(s) that implement it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-0 (regression-first) | §Sequencing, per-step "Regression test", §Verification gate | Partial | No stated exemption for docs-only (FR-H5c) or optional (FR-F1c/F2b) sub-reqs that cannot fail red-on-main (see R1-F8). |
| FR-0a (flag-don't-crash) | Steps 4, 5 | Full | — |
| FR-0b (idempotency) | Step 2 test (iv), §Verification gate | Full | — |
| FR-F13a (renderer defensive) | Step 1a | Full | — |
| FR-F13b (emitter canonical) | Step 1b | Partial | Step 1b says "Locate the boolean-default emission; confirm the prose→default mapping" — locus not yet pinned to a `file:line`, unlike every other step. |
| FR-F3b-i (field `@unique`) | Step 2a | Full | — |
| FR-F3b-ii (`@@unique` composite) | Step 2b | Full | — |
| FR-F3b-iii (no dup of `@@id`) | Step 2b ("Skip any compound-unique tuple identical to `@@id`") | Full | — |
| FR-F1a (value-level sanity) | Step 6a | Partial | Record has no warning tier in the current model (R1-S2/R1-F3); OQ-7 unresolved. |
| FR-F1b (author guidance docs) | Step 6c | Full | — |
| FR-F1c (optional detection) | Step 6c (optional) | Partial | No disambiguator for truncation vs genuine single value (R1-F4); no red-on-main test possible (R1-F8). |
| FR-F2a (parse-time guard) | Step 4a, 4b | Partial | Empty-vs-absent `order` sentinel ambiguity (R1-S6). |
| FR-F2b (optional auto-derive) | Step 4c | Partial | Deferred/optional; depends on threading `known_enums`. |
| FR-H3 (workspace clear error) | Step 5 | Full | — |
| FR-F3-i (grammar cardinality) | Step 3 (full) | Partial | Gated by OQ-4; default landing unclear (R1-S4). |
| FR-F3-ii (emit `X?` + `@unique`) | Step 3 (full) | Partial | No migration-safety for existing multi-row data (R1-S3/R1-F1). |
| FR-F3-iii (flag unsupported) | Step 3 (minimal) | Full | Should be the *default* first landing (R1-F2). |
| FR-H4a (ACCEPT-but-inert) | Step 7 | Partial | Apply-refusal locus misattributed (R1-S1/R1-F5); qualifier string should reuse `CaptureCode` (R1-F6). |
| FR-H4b (no silent partial) | Step 7 test | Partial | Preview (`would_apply`) parity not asserted (R1-S8/R1-F9). |
| FR-H4c (non-goal: no floor widening) | §Sequencing note, Step 7 | Full | — |
| FR-H5a (SDK-side flag) | Step 8a | Full | — |
| FR-H5b (cross-repo, tracked) | Step 8b | Full | Correctly scoped out as separate cap-dev-pipe PR. |
| FR-H5c (docs contract) | Step 8c | Partial | Documents OQ-6 precedence before OQ-6 is decided from the code (R1-S5/R1-F7). |
