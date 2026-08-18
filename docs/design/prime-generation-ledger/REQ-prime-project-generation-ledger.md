# REQ — Prime-Project Generation Ledger + Cross-Project Index

- **Schema:** det-req/0.1
- **Name:** prime-project-generation-ledger
- **Maturity:** 0.1 (build-ready)
- **Status:** I1–I3 BUILT + landed (`d0de1087`) — the data spine (FR-1 identity · FR-2 registry ·
  FR-3 auto-derive) ships, proven by reproducing the portal-v2 row from its real manifests. FR-4 (CLI) ·
  FR-6 (liveness oracle) · FR-5 (postmortem hook) = I4–I6, the queryable/trustworthy/live surface, remain.
- **Derives from:** `INSTANTIATION_prime-project-generation-ledger.md` (the `/reflective-instantiation`
  loop that named cell C1). **Built ON** `src/startd8/contractors/batch_postmortem.py` — an extension,
  not a reinvention.

> **One-line:** give the Prime Contractor a durable, auto-derived record of **every project it works
> on and every run per project** (what/where/when/cost/status/artifacts), plus a **cross-project index**
> — by adding a *project-identity seam* to the existing seed-centric `batch_postmortem.py` and a thin
> global registry beside `~/.startd8/costs.db`.

---

## Objectives

- **O-1 — Answer the four cross-project questions.** (a) Which projects has Prime touched? (b) For
  project X, every run and when (what/where/when/cost/status/artifacts)? (c) Cumulative cost/status per
  project? (d) Where are run Y's artifacts?
  **Verify:** a CLI query over ≥2 projects returns each of (a)–(d) from real recorded runs.
  **Signal:** `startd8 prime-ledger list` non-empty after two projects generated.
- **O-2 — Extend, don't reinvent.** Reuse `BatchLedger`/`TaskLedgerRecord`/`RunSnapshot` and the
  auto-derive path (`generation-manifest.json` → row); the project layer is additive.
  **Verify:** no field removed from `batch_postmortem.py`; existing batch-ledger consumers unaffected
  (their tests pass unedited).
- **O-3 — Trust by construction, not by hand.** Every row is auto-derived from run artifacts and a
  `verify`-style oracle re-checks that cited artifact paths resolve and costs/counts match source.
  **Verify:** `startd8 prime-ledger verify` flags a row whose artifact path is absent (PHANTOM) or
  whose cost drifts from its `generation-manifest.json`.

## Non-goals

- **NR-1** — NOT a model-performance benchmark (that is `benchmark_matrix/aggregate.py`; different
  SUBJECT). No model ranking.
- **NR-2** — NOT a replacement for `batch-ledger.json`. The per-project batch ledger stays the
  authoritative task-level detail; the new layer **points at it**, never duplicates `history[]`.
- **NR-3** — NOT the delivery ledger's cross-project rollup (deferred cell C4). Reserve an
  `artifacts.delivery_ledger` pointer; do not absorb requirement→satisfaction data now.
- **NR-4** — NOT auto-committed or synced anywhere; the registry is local user state under `~/.startd8/`.

---

## Functional Requirements

- **FR-1 — Project-identity field on the ledger.**
  Add optional `project_id` + `project_path` to `BatchLedger` (empty-default, so existing ledgers
  deserialize unchanged). Resolve `project_id` from `project-context.yaml` `spec.project.id` when
  present, else from the project-root dir name.
  **Touches:** `src/startd8/contractors/batch_postmortem.py` (add fields + serialize/deserialize),
  `tests/unit/contractors/test_batch_postmortem.py`.
  **Verify:** a v0-shaped `batch-ledger.json` (no project fields) round-trips through
  `_deserialize_ledger`→`_serialize_ledger` byte-identical except the two new empty keys; a ledger built
  with a `project_id` preserves it.

- **FR-2 — Global generation-ledger registry.**
  New module `src/startd8/contractors/generation_ledger.py`: a `ProjectGenerationLedger` (per-project
  file) + `GenerationLedgerIndex` (cross-project) persisted under `~/.startd8/generation-ledger/`
  (`projects/<project-id>.json` + `index.json`), atomic-write (`.tmp`+rename, the `save_ledger` pattern
  at `batch_postmortem.py:332-341`).
  **Touches:** `src/startd8/contractors/generation_ledger.py`,
  `tests/unit/contractors/test_generation_ledger.py`.
  **Verify:** recording two runs from two `project_id`s yields two `projects/*.json` files and one
  `index.json` listing both; `~/.startd8` home is overridable via env for the test (no real HOME write).

- **FR-3 — Auto-derive a run row from real artifacts.**
  `record_run(project_root)` reads `generation-manifest.json` (cost/tokens/features/`generated_at`) and
  the sibling `batch-ledger.json` (batch_id/seed/run counts), joins them into one run row with a
  `cost_by_provider`/`model_mix` rollup and an `artifacts{role: abs-path}` map, appends to the
  per-project ledger, and upserts the index.
  **Touches:** `src/startd8/contractors/generation_ledger.py`,
  `tests/unit/contractors/test_generation_ledger.py` (fixture = portal-v2's real manifests, copied into
  `tests/.../fixtures/`).
  **Verify:** recording against the portal-v2 fixture reproduces the §4.1 row exactly — cost
  `2.9375809999999993`, 16/16 passed, 5×`claude-sonnet-4-6` + 11×`startd8-coder`, 10 artifact paths.

- **FR-4 — Cross-project query surface (CLI).**
  `startd8 prime-ledger list` (all projects: id · runs · last-run · cumulative cost · status),
  `... show <project-id>` (every run: what/where/when/cost/status), `... artifacts <project-id> <run-id>`
  (the run's artifact map). `--json` on each for CI.
  **Touches:** `src/startd8/cli.py` (or a `cli_prime_ledger.py` sub-app),
  `tests/unit/test_cli_prime_ledger.py`.
  **Verify:** with two recorded projects, `list --json` returns both; `show portal-v2 --json` returns
  the one run with its cost; `artifacts portal-v2 portal-v2-preview` prints the 10 paths.

- **FR-5 — Register a run from the postmortem hook.**
  Wire `record_run` into `scripts/run_prime_postmortem.py` right after `save_ledger`
  (`run_prime_postmortem.py:344-345`) — the batch ledger is written, then the project layer records the
  run. Guarded/opt-out via a flag so batch-only runs are unaffected.
  **Touches:** `scripts/run_prime_postmortem.py`, `tests/unit/scripts/test_run_prime_postmortem.py`.
  **Verify:** running the postmortem on the portal-v2 fixture writes both `batch-ledger.json` (unchanged
  behavior) and a `~/.startd8/generation-ledger/projects/portal-v2.json`.

- **FR-6 — Liveness oracle (the trust-model improvement).**
  `startd8 prime-ledger verify [<project-id>]`: for each recorded run, re-check every `artifacts{}` path
  resolves on disk (PHANTOM if absent) and the recorded `cost_usd`/feature counts still match the cited
  `generation-manifest.json` (DRIFT if not). Advisory exit codes (0 clean / 1 findings), never mutating.
  **Touches:** `src/startd8/contractors/generation_ledger.py`, `tests/unit/contractors/test_generation_ledger.py`.
  **Verify:** deleting a fixture artifact makes `verify` report PHANTOM for that run; editing a recorded
  cost makes it report DRIFT; the pristine portal-v2 row verifies clean.

---

## Iteration plan (acyclic)

```
I1 (FR-1)  project-identity field on BatchLedger        [no dep]
I2 (FR-2)  global registry module + persistence         [dep: none — pure new module]
I3 (FR-3)  auto-derive run row from artifacts            [dep: I1, I2]
I4 (FR-6)  liveness oracle                               [dep: I2, I3]
I5 (FR-4)  CLI query surface                             [dep: I2, I3]
I6 (FR-5)  postmortem-hook wiring (live end-to-end)      [dep: I1, I3]
```

- **DAG check:** I1,I2 are roots; I3 joins them; I4/I5 depend on I3; I6 closes the loop. No cycle.
- **Gate:** I1–I3 are the spine (the ledger records real runs); I4–I6 make it queryable + trustworthy +
  live. Ship I1–I3 first (the data exists and is correct), then the surface.
- **Byte-identity guard on I1:** the existing `test_batch_postmortem.py` suite must pass **unedited**
  except for the two new-field assertions (proves NR-2 — batch consumers unaffected).

## Open seams (folded from the instantiation findings §5)

- **F-3 (model-mix):** the `cost_by_provider`/`model_mix` rollup is a cross-artifact join
  (`generation-manifest.json` per-feature `provider`) the family currently makes nobody do — FR-3 owns it.
- **F-4 (four identities):** pin the composite key `(project_id, batch_id, run_id)`; treat the
  `run-provenance.json` uuid as an artifact-pointer target, not an identity (FR-3).
- **C4 (deferred):** `artifacts.delivery_ledger` is reserved `null` today (portal-v2 has none); a later
  additive REQ rolls delivery ledgers up cross-project without touching this schema.
