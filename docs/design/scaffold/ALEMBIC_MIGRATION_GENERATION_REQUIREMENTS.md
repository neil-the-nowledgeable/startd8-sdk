# Alembic Migration Generation (OQ-SCAF-2) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-10
**Status:** Partially IMPLEMENTED 2026-06-10 — **FR-MG-1 (scaffold completion) + FR-MG-5 (create_all
demotion + drift guard) shipped & tested** (247 passed). FR-MG-2/3/6 (fork-B baseline + delta emitter +
check) pending OQ-SCAF-2c (the "previous-snapshot source" decision) — the focused increment-2 build.
**Scope:** Close the long-deferred **OQ-SCAF-2**: give a generated app a way to evolve a **persistent**
database to match an updated contract, so a contract field-add stops silently diverging from
`app.db`. Driven by strtd8 `SDK_QUICK_WINS_2026-06-10` #5 + `SDK_RESUME_LIBRARY_ARCHETYPE_GAPS` P0-3.
**Requested by:** strtd8 app team. **Live impact:** `/workspace` 500'd on the real DB on 2026-06-10
(`no such column` — `JobDescription.{status,appliedDate,…}` added to the contract never reached the
persistent `app.db`; green in tests because tests build a fresh `create_all` DB).
**Related:**
- `src/startd8/scaffold_codegen/renderers.py` — `render_alembic_ini` / `render_alembic_env` (today's
  partial Alembic emission); `render_scaffold` (the gated artifact list)
- `src/startd8/manifest_extraction/prisma_emitter.py` — `semantic_diff` (the contract-vs-contract diff)
- `src/startd8/languages/prisma_parser.py` — `parse_prisma_schema` (models/fields/enums)
- strtd8: `SDK_QUICK_WINS_2026-06-10.md` #5, `SDK_RESUME_LIBRARY_ARCHETYPE_GAPS_2026-06-10.md` P0-3

---

## 0. Planning Insights (Self-Reflective Update)

> v0.1 took the strtd8 reports' framing verbatim: *"`generate` emits/refreshes an Alembic migration
> for contract deltas ($0, deterministic — the same diff the emitter already computes for `--check`)."*
> A code-investigation pass over `scaffold_codegen` + how Alembic autogenerate actually works produced
> four corrections — two of them change the feature's shape.

| v0.1 assumption (from the reports) | Planning discovery | Impact |
|---|---|---|
| Autogenerate is "$0, deterministic — the same diff as `--check`" | **False premise.** Alembic `--autogenerate` diffs `SQLModel.metadata` against a **live database connection** (it reflects the actual DB). `--check`'s diff is doc-derived-schema vs `schema.prisma` (text/AST, $0). These are *different diffs over different inputs*. Autogenerate is **inherently runtime + DB-stateful** — it needs the app importable AND a DB to reflect. | The feature splits into a **design fork** (OQ-SCAF-2a): **(A)** shell out to real autogenerate (accurate, needs app venv + DB, not $0) vs **(B)** a deterministic **contract-delta** revision emitter (diff old vs new `schema.prisma`, emit additive ops, $0, no DB) — *not* autogenerate at all. |
| The scaffold already supports migrations; we just add a runner | The scaffold emits only `alembic.ini` + `alembic/env.py`. **No `script.py.mako`, no `versions/`, no baseline revision.** `alembic revision` *fails* without the mako template; `alembic upgrade head` has nothing to run. So a generated app **cannot generate or apply any migration today** — it survives only on `create_all`. | **Scaffold completion is a prerequisite for either fork**: emit `script.py.mako`, a `versions/` dir, and a baseline revision. This is new required work the reports didn't name. |
| "Never a drop on existing data" is a property we add to autogenerate | Real autogenerate *will* emit `drop_column`/`drop_table` when metadata lacks something the DB has (and SQLite can't `ALTER`-drop cleanly — alembic uses batch/table-rebuild). The safety property is **free in fork B** (emit only additive ops) but must be **enforced/guarded in fork A** (filter or fail on destructive ops). | The OQ-SCAF-2 "migration-preserves-rows" blocker is **dissolved by fork B** (additive-by-construction) and only **managed** by fork A. Strong argument for B as the default. |
| `create_all` is just a convenience to keep | `create_all` is the *active cause* of the drift: it creates missing tables but never alters, so it silently masks the missing migration until a field-add 500s. | Whichever fork: `create_all` must be **demoted to dev-bootstrap-only** (documented + a drift guard), or the duality keeps biting. This is FR-MG-5. |

**Resolved open questions:**
- **OQ-SCAF-2 (the original "migration-preserves-rows" blocker) → dissolved by fork B**: an
  additive-only contract-delta emitter never drops, so the blocker that deferred this evaporates.
- **"$0 deterministic" claim → only true for fork B**, and only for additive deltas. Fork A is neither.

**Still open:** **OQ-SCAF-2a** — the A-vs-B fork (and a possible hybrid). §4.

---

## 1. Problem Statement

A generated app boots with `init_db()` → `SQLModel.metadata.create_all`, which **creates missing
tables but never alters existing ones**. The scaffold also emits a *partial* Alembic setup
(`alembic.ini` + `env.py`) but **no `script.py.mako`, `versions/`, or baseline** — so migrations
can't actually be generated or applied. Net: on a **persistent** DB, every contract field-add
silently diverges from `app.db` until the ORM 500s with `no such column`; tests never catch it (fresh
`create_all` DB). The contract is derived end-to-end *except* it cannot evolve a populated database.

| Surface | Today | Target |
|---|---|---|
| New app, empty DB | `create_all` makes all tables | unchanged (or baseline `upgrade head`) |
| Existing app, contract gains a field | **silent drift → runtime 500** | a generated **additive** migration the operator applies |
| `alembic revision` in a generated app | **fails** (no `script.py.mako`) | works (scaffold completed) |
| Drop/rename a field | n/a | **out of scope** — manual, never auto-emitted (data-loss) |

## 2. Functional Requirements

> `Verify:` is the asserting test. FR-MG-3 is fork-dependent (§4).

- **FR-MG-1 — Complete the Alembic scaffold.** `generate scaffold` (when `migrations` is on) emits a
  runnable Alembic setup: the existing `alembic.ini` + `env.py`, **plus** `alembic/script.py.mako` and
  an `alembic/versions/` directory (with a `.gitkeep` or baseline). Verify: a scaffolded project can
  run `alembic revision -m x` without error (the mako exists); `render_scaffold` lists the new files.

- **FR-MG-2 — Baseline revision.** Emit an initial revision whose `upgrade()` creates the full current
  model set (so `alembic upgrade head` on an empty DB reproduces what `create_all` would, and `stamp
  head` adopts an existing one). Verify: the baseline `upgrade()` contains `create_table` for every
  contract model; `down_revision = None`.

- **FR-MG-3 — Generate a migration for a contract delta** *(shape per OQ-SCAF-2a)*. A command produces
  a revision that evolves the DB to the current contract. **Default (fork B): additive-only**, derived
  deterministically from the diff between the previously-promoted `schema.prisma` and the current one —
  `add_column` for new fields, `create_table` for new models — **never** a drop. Verify: adding a field
  to the contract yields a revision whose `upgrade()` is exactly that `add_column` (nullable or with a
  server_default for NOT NULL on SQLite), `downgrade()` the inverse; a *removed* field yields **no**
  destructive op (a logged note instead).

- **FR-MG-4 — Operator-applied, never auto-applied.** No SDK command runs `alembic upgrade` against a
  populated DB. `generate migrate` writes the revision file only; applying it is an explicit operator
  step (`alembic upgrade head`). Verify: running the generator mutates only `alembic/versions/`, never
  the DB.

- **FR-MG-5 — Demote `create_all` to dev-bootstrap; add a drift guard.** Document `create_all` as
  dev/test bootstrap only, and have `init_db` (dev mode) **warn loudly** when the reflected DB columns
  don't match `metadata` (the signal that a migration is pending) instead of limping to a 500. Verify:
  a DB missing a contract column triggers the drift warning at boot, naming the table/column.

- **FR-MG-6 — `--check` for DB-behind-head.** A check mode reports whether a target DB is behind the
  latest revision (exit non-zero), for CI/pre-deploy. Verify: a DB at an older revision → non-zero +
  the pending revision id; an up-to-date DB → zero.

## 3. Non-Requirements

- **No auto-apply to a populated DB** (FR-MG-4). The operator owns `upgrade`.
- **No destructive ops auto-emitted.** Drops/renames/type-narrowing are manual (data-loss class);
  fork B never emits them, fork A must guard them. A column/model removed from the contract is
  reported, not dropped.
- **Not a general migration tool.** Only SQLite (the locked target) + the additive delta classes the
  contract expresses; exotic Alembic features are out.
- **No LLM.** Deterministic.

## 4. Open Questions

- **OQ-SCAF-2a — A vs B (THE fork).**
  - **A — shell out to real `alembic revision --autogenerate`.** *Pro:* accurate; catches actual
    DB-vs-metadata drift incl. things the contract diff can't see; reuses alembic's op generation.
    *Con:* needs the app's venv (alembic installed) + the app importable + a live DB; **not $0/
    deterministic**; emits destructive ops that must be filtered/guarded; harder to unit-test (needs a
    subprocess + DB fixture).
  - **B — deterministic contract-delta emitter (recommended).** Diff previously-promoted vs current
    `schema.prisma` (reuse `semantic_diff`), emit an Alembic revision file with additive ops directly —
    **no alembic run, no DB**. *Pro:* $0, deterministic, on-charter (Class-2 determinism); additive-by-
    construction dissolves the OQ-SCAF-2 preserves-rows blocker; unit-testable as text. *Con:* only sees
    contract-expressible additive deltas (new model/field); a hand-edited DB or a type-change still
    needs manual `alembic revision --autogenerate` (which the completed env.py supports).
  - **Hybrid:** B as `generate migrate` default for the common additive case; rely on the
    FR-MG-1-completed env.py for the operator to run real autogenerate for the rare type-change. Likely
    the right end state.
- **OQ-SCAF-2b — NOT NULL adds on SQLite.** A new required column needs a `server_default` to satisfy
  existing rows (the strtd8 fix used `VARCHAR(12) NOT NULL server_default 'discovered'`). Derive the
  server_default from the contract's `@default(...)`? (Lean: yes — and fail loud if a required field
  has no `@default`.)
- **OQ-SCAF-2c — Where does "previously-promoted schema" come from for the diff (fork B)?** The
  `_superseded-handauthored/` archive? The last revision's recorded model set? A checksum sidecar? Must
  be unambiguous and survive across runs.

## 5. Dependencies & sequencing

- **FR-MG-1 + FR-MG-2 (scaffold completion + baseline) are prerequisites for either fork** and are
  independently valuable (today migrations can't run at all). Do these first.
- Then settle **OQ-SCAF-2a** → implement FR-MG-3 in the chosen shape.
- FR-MG-5 (create_all demotion + drift guard) is independent and cheap — a strong standalone safety
  win even before FR-MG-3.
- **Shared-floor:** affects every app on a non-fresh DB (the sibling Generator included).

## 6. Acceptance

1. A scaffolded project runs `alembic revision -m x` and `alembic upgrade head` (FR-MG-1/2).
2. (fork B) Adding `JobDescription.appliedDate date` to the contract → `generate migrate` emits a
   revision whose `upgrade()` is one `add_column` (server_default'd if required), `downgrade()` the
   inverse; re-running is idempotent (no second revision for the same delta).
3. A removed contract field emits **no** destructive op — a logged note only (FR-MG-3 / non-req).
4. `init_db` in dev warns (not 500s) when `app.db` is missing a contract column (FR-MG-5).
5. `generate migrate --check` exits non-zero when a DB is behind head (FR-MG-6).

---

*v0.2 — Post-planning self-reflective update. The reports' "$0 autogenerate = the `--check` diff"
premise was false (autogenerate is runtime + DB-stateful); the feature reframes to a recommended
deterministic additive-delta emitter (fork B), with scaffold-completion (FR-MG-1/2) as a newly-found
prerequisite and `create_all` demotion (FR-MG-5) as an independent safety win. OQ-SCAF-2a (A vs B vs
hybrid) is the one decision left before build.*
