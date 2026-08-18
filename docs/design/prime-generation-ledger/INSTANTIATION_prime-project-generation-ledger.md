# Reflective Instantiation — the Prime-Project Generation Ledger

**Loop:** `/reflective-instantiation` (the downward twin — a named product space → its empty cells).
**Captured:** 2026-08-18 · **Scope:** the *ledger family* the requirements-visualization work recently
adopted, descended one coordinate to its unbuilt member. **Mode:** design-on-paper + one real seeded
occupant; no source modified.

> **The abstraction:** the LEDGER FAMILY — a durable record of *what a process touched, at what
> granularity, rolled up over what scope, under what trust model*. Four occupants already exist. This
> loop realizes the empty cell they collectively imply: a **per-project, cross-run Prime-Contractor
> generation ledger with a cross-project index**.

---

## §1 — Product space (Phase 1: Name)

### The algebra

```
Ledger = SUBJECT × GRANULARITY × ROLLUP-SCOPE × TRUST-MODEL
```

- **SUBJECT** — what the rows are *about* (a requirement/FR delivery · a navigator-loop node · a
  Prime *task* · a Prime *requirement→satisfaction* dossier · a Prime *project*).
- **GRANULARITY** — the row's atomic unit (per-artifact · per-loop-node×run · per-task×run ·
  per-requirement · per-project×run).
- **ROLLUP-SCOPE** — the widest question it answers without leaving the file (one session · one loop ·
  one seed-batch · one project · **all projects**).
- **TRUST-MODEL** — how a reader is meant to believe a row (hand-maintained + verify-out-of-band ·
  auto-derived-from-run-artifacts · projection-from-upstream-artifacts).

### The invariant (one sentence)

> **Every ledger in the family is a durable, append-structured record that lets a reader answer
> "what happened to X across its history, and can I trust each row" without re-running the work —
> differing only in what X is, how finely it is recorded, how far it rolls up, and how a row earns
> belief.**

### Coverage table (existing occupants — all Built)

| Variant | SUBJECT | GRANULARITY | ROLLUP-SCOPE | TRUST-MODEL | Built? | Cite (path:line) |
|---|---|---|---|---|---|---|
| **Session ledger** | requirement/FR delivery | per-artifact row | one session (grouped by state) | hand-maintained, DRIFTS → verify via FR-tag commits+tests+`verify_ledger.py` | yes | `docs/design/requirements-visualization/SESSION_LEDGER_specs-and-open-tasks.md:8-12` |
| **Pilot loop ledger** | a navigator loop node (e.g. `FR-4`) | per-node × per-run record | one loop (moving `pilot_score`) | auto-derived from each loop pass's metrics | yes | `docs/design/requirements-visualization/_pilot/ledger.json:2-21` |
| **Batch ledger** | a Prime *task* | per-task × per-run (`history[]`) | one **seed-batch** (`batch_id`=SHA256(seed)) | auto-derived from `prime-result.json` history | yes | `src/startd8/contractors/batch_postmortem.py:76-88` |
| **Delivery ledger** | a Prime *requirement→satisfaction* | per-requirement (`work_items`/`evidence`) | one project (single run's projection) | projection from postmortem+traceability, loud honest skips | yes | `src/startd8/contractors/prime_delivery_ledger.py:39-55` |

**Reading the table:** the batch ledger already carries the *machinery* the empty cell needs —
`TaskLedgerRecord.history` (task across runs, `:51-58`), `RunSnapshot` (per-run summary, `:61-73`),
cumulative cost/velocity (`:539-568`). But its ROLLUP-SCOPE column reads **"one seed-batch"**, not
"one project" or "all projects" — and that is the whole gap.

---

## §2 — Empty-cell census (Phase 2)

| Cell (axis coordinates) | Predicted artifact shape |
|---|---|
| **C1 — SUBJECT=Prime-project · GRANULARITY=per-project×per-run · ROLLUP-SCOPE=cross-project index · TRUST=auto-derived** | A durable ledger keyed by **project identity** (not seed), each project holding an append list of *runs* (what/where/when/cost/status/artifacts), **plus a cross-project registry** answering: which projects has Prime touched? for project X, every run + when + cost + status + where its artifacts are? cumulative cost/status per project? **This is the primary cell.** |
| **C2 — SUBJECT=Prime-project · ROLLUP=one project · GRANULARITY=per-run · TRUST=auto-derived** | The per-project *file* alone, no cross-project index. Degenerate sub-case of C1 (the project-scoped half). |
| **C3 — SUBJECT=model/agent · GRANULARITY=per-model×per-run · ROLLUP=cross-project · TRUST=auto-derived** | A cross-project *model-performance* ledger (which model, over all projects, at what cost/pass-rate). The benchmark matrix already partly occupies this (`benchmark_matrix/aggregate.py`). |
| **C4 — SUBJECT=requirement · GRANULARITY=per-requirement · ROLLUP=cross-project · TRUST=projection** | A cross-project *delivery* index (every requirement Prime satisfied, across all projects). Extends the delivery ledger's scope column. |

---

## §3 — Adjudication (Phase 3)

| Cell | Verdict | Reason |
|---|---|---|
| **C1** | **natural-next (with a revealing-absence seam)** | The abstraction squarely predicts it and there is a real consumer need. The seam: `batch_postmortem.py` has the run-history machinery but is **seed-centric** — `batch_id = derive_batch_id(SHA256(seed))` (`:144-155`), `seed_path`/`seed_checksum` are the only identity fields on `BatchLedger` (`:80-82`); there is **no `project_name`/`project_path`** and **no registry that indexes batches across projects**. A seed edit *forks* the batch (`:176-182`), so today "the portal-v2 project" is invisible as a first-class entity — you can only find its batch by knowing its seed hash. The missing seams: (a) a **project-identity** field on the ledger, and (b) a **cross-project registry** + discovery entry point. Both are additive to `batch_postmortem.py`; realize C1's data now, route the seam-fix to the spec (§4.2). |
| **C2** | **correct-absence (subsumed)** | The project-scoped file without the index is just C1 minus its index; not worth a separate artifact. Ship it *inside* C1. |
| **C3** | **correct-absence (owned elsewhere)** | Cross-project *model* skill is the benchmark matrix's job (`benchmark_matrix/aggregate.py` `rank_models_by_quality`/`_by_consistency`). A generation ledger records *what a project's runs did*, not *which model is best* — different SUBJECT. Leave empty; note the owner. |
| **C4** | **natural-next but deferred** | A genuine cell, but the delivery ledger is a single-run projection with honest merge-SHA skips (`prime_delivery_ledger.py:150-173`); making it cross-project is a *second* instantiation. The generation ledger (C1) can *link to* each run's delivery-ledger artifact without absorbing it. Defer; the C1 spec reserves an `artifacts.delivery_ledger` pointer so C4 is a later additive rollup. |

**Over-fill guard satisfied:** two of four cells are `correct-absence`. C1 is the single realized cell;
C4 is a named-but-deferred natural-next (linked, not absorbed). No symmetry-worship.

### The TRUST-MODEL improvement (called out per the loop's revealing-absence discipline)

The abstraction's *first-listed* occupant (the session ledger) is **hand-maintained and drifts** — its
own standing caveat says "verify by FR-tag commits + tests, never by this list"
(`SESSION_LEDGER...md:8-9`), and it needed a `verify_ledger.py` oracle bolted on to be trustworthy.
**C1 must NOT inherit that trust model.** A *generation* ledger has a decisive advantage the session
ledger lacks: every row is **auto-derivable from real run artifacts** (`generation-manifest.json`,
`batch-ledger.json`, `run-provenance.json`) — the same posture the pilot loop ledger and batch ledger
already take. So C1's TRUST-MODEL is **auto-derived + a `verify_ledger`-style oracle** (re-check that
each recorded run's cited artifact paths still resolve on disk and each cost/count still matches the
source manifest) — an *improvement* on the abstraction, not a copy of its weakest member. This is the
instantiation feeding a fix back up: the family's trust axis gains a strictly-better value.

---

## §4 — Realizability (Phase 4)

### §4.1 — The realized cell: portal-v2's generation-ledger entry (real data)

Materialized **from portal-v2's actual artifacts**, not invented. Every number below was read from
disk:

| Field | Value | Source (path:line) |
|---|---|---|
| project id | `portal-v2` | `pipeline-output/portal-v2-preview/project-context.yaml:8` |
| run id | `portal-v2-preview` | `batch-ledger.json:284` |
| batch id | `batch-4e94a4edc329` | `batch-ledger.json:2` |
| seed checksum | `4e94a4edc329…529538` | `batch-ledger.json:6` |
| generated at | `2026-08-13T23:10:15.959377+00:00` | `.startd8/generation-manifest.json:145` |
| features attempted / passed / failed | 16 / 16 / 0 | `batch-ledger.json:286-288` |
| total tasks in batch (remaining) | 21 (5 remaining) | `batch-ledger.json:5,290-291` |
| total cost | **$2.9375809999999993** | `.startd8/generation-manifest.json:141` |
| input / output tokens | 1,425,139 / 601,388 | `generation-manifest.json:142-143` |
| model time (ms) | 7,522,337 | `generation-manifest.json:144` |
| feature list (16) | PI-002b, PI-003, PI-004a/b, PI-005a/b, PI-006a/b, PI-007, PI-008a/b, PI-009, PI-010a/b, PI-011a/b | `generation-manifest.json:11-139` |

**Cost split observed in the real data (a finding — see §5):** only 5 of the 16 features carried
non-zero cost (the Sonnet features: PI-002b $0.61, PI-006a $1.08, PI-006b $0.48, PI-007 $0.40,
PI-010a $0.36); the other 11 ran on `ollama:startd8-coder` at **$0.00** (`generation-manifest.json`
per-feature `provider`). The ledger row records this model-mix, which neither `batch-ledger.json` nor
`generation-manifest.json` surfaces as a rollup.

The concrete artifact is the sibling file **`LEDGER_prime-project-generation_portal-v2.json`** (real
JSON) with a short markdown view inline in its header comment / the table above.

### §4.2 — Where the central cross-project registry lives (proposed + justified)

**Proposal: `~/.startd8/generation-ledger/`** — a global (per-user) registry, with per-project files
`~/.startd8/generation-ledger/projects/<project-id>.json` and one index
`~/.startd8/generation-ledger/index.json`.

**Justification, grounded in where things write today:**
- The per-batch `batch-ledger.json` writes to `<project-root>/.cap-dev-pipe/pipeline-output/`
  (`scripts/run_prime_postmortem.py:307-308`, `_resolve_pipeline_base(output_dir)`). That is
  **per-project and gitignored** — correct for batch detail, but structurally **cannot answer a
  cross-project question**, because no project's tree knows about another's.
- `~/.startd8/` is the SDK's **already-established cross-project home**: it holds `costs.db`,
  `discovered_models.json`, `benchmarks/`, `config.json` — user-global, project-independent state
  (verified: `ls ~/.startd8/`). A cross-project *generation* index belongs beside `costs.db`, which is
  itself a cross-project cost record.
- Neither the SDK repo nor the benchmarking repo is the right home: the SDK is *code* (a registry there
  would be committed churn), and the benchmarking repo is *one consumer* — the whole point of C1 is that
  Prime touches **many** projects, so the index must live above any single one.

**The per-project file** stays *discoverable from both directions*: the global index holds a pointer to
each project's canonical run detail (its `.cap-dev-pipe/pipeline-output/batch-ledger.json`), so
`~/.startd8/generation-ledger/` is a **thin cross-project index over the authoritative per-project
batch ledgers** — it does not duplicate task-level history, it *points at* it. (This mirrors how
`run-provenance.json` already stores absolute artifact paths, `:66-71`.)

### §4.3 — Verified-not-existing

Grepped `src/` + `scripts/`: no `project_name`/`project_path` field on any ledger, no
`~/.startd8/generation-ledger`, no cross-project index or discovery entry point exists. `batch_id` is
the only cross-run key and it is seed-derived. C1 is a genuine gap, not a discoverability problem.

### §4.4 — Next action

Two artifacts realize C1 (both created, neither commits): the **portal-v2 ledger JSON** (§4.1, the
first row with real data) and the **build-ready spec** (§4.2's registry, built *on*
`batch_postmortem.py`). See the spec doc for FRs + iteration plan.

---

## §5 — Reflective findings (belief → actual)

What materializing portal-v2's REAL data revealed the abstraction (and `batch_postmortem.py`) lacks:

| # | Belief (going in) | Actual (from the bytes) | Consequence for the design |
|---|---|---|---|
| **F-1** | "The batch ledger tracks a *project's* runs." | It tracks a **seed-hash's** runs. `BatchLedger` has `seed_path`/`seed_checksum` but **no project field** (`batch_postmortem.py:80-82`); `project-context.yaml` (`spec.project.id: portal-v2`) lives in a *different* file the ledger never reads. | The seam is a **project-identity field**, not a rewrite. The spec adds `project_id`/`project_path` to the ledger (additive, empty-default). |
| **F-2** | "A project has one batch." | A project can have **many** batches — any seed edit forks a new `batch-` id (`:176-182`). portal-v2 has one *today*, but the identity model guarantees drift: the cross-project index must be **project→[batches]→[runs]**, not project→runs. | The index's per-project entry holds a *list* of batch ids, each pointing at its own `batch-ledger.json`. |
| **F-3** | "Cost is a single number per run." | Cost is a **model-mix**: 5/16 features cost money ($2.94 total), 11/16 were $0 on Ollama (`generation-manifest.json` per-feature `provider`). The batch ledger's `RunSnapshot.cost_usd` (`:73`) flattens this; the model attribution is only in `generation-manifest.json`, a *different* artifact. | The ledger row records a `cost_by_provider`/`model_mix` rollup — a cross-artifact join the family currently makes nobody do. This is real cross-project value (which projects lean on paid models?). |
| **F-4** | "Run identity = batch id." | Three identities coexist and none is the project: `batch_id` (seed hash, `batch-ledger.json:2`), `run_id` (`portal-v2-preview`, human-set, `:284`), and the manifest `generated_at` timestamp (`:145`). The `run-provenance.json` adds a *fourth* uuid `run_id` (`:2`) that is a different thing entirely (a manifest-export run, not the Prime run). | The ledger must be explicit about which id is the join key. Spec pins **`(project_id, batch_id, run_id)`** as the composite key and treats the provenance uuid as an *artifact pointer target*, not an identity. |
| **F-5** | "Artifacts are self-locating." | The run's real artifacts (`generation-manifest.json`, `prime-postmortem-report.json`, `batch-ledger.json`, the `portal-v2-preview/` run dir with 20 files) are scattered across **two roots** — `<proj>/.startd8/` and `<proj>/.cap-dev-pipe/pipeline-output/` — with no single manifest tying them to the project entity. `run-provenance.json` lists *some* outputs by absolute path (`:24-61`) but not the generation manifest or batch ledger. | The ledger row's `artifacts{}` map is the **missing single index** of a run's outputs by role → absolute path. This is the "where are run Y's artifacts?" question the user asked, and today nothing answers it. |
| **F-6** | "The family's trust model is uniform." | It is not — the session ledger is hand-maintained/drifting (`SESSION_LEDGER...md:8`) while the pilot + batch ledgers are auto-derived. The abstraction's *canonical listed occupant* is its *weakest* trust member. | C1 deliberately takes the **stronger** trust value (auto-derived + a resolve-check oracle), improving the family's trust axis rather than inheriting the drift. (§3 improvement.) |

---

## §6 — Loop result

- **1 natural-next cell realized** (C1) with real portal-v2 data.
- **1 natural-next cell deferred + linked** (C4, cross-project delivery — pointer reserved).
- **2 correct-absences** (C2 subsumed, C3 owned by the benchmark matrix).
- **1 revealing-absence seam named** — project-identity + cross-project registry, additive to
  `batch_postmortem.py`; routed to the spec.
- **1 trust-model improvement fed back up** — the generation ledger is auto-derived, not hand-maintained.

The abstraction is **not** complete (C1 was a true empty cell), and it was **not** too narrow (only one
cell was natural-next-and-ready). Healthy instantiation.
