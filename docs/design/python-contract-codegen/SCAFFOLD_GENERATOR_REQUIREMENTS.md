# Manifest-Driven Scaffold Generator — Requirements

**Version:** 0.1 (Draft — pre-planning, pre-CRP)
**Date:** 2026-06-04
**Status:** Draft for review
**Companion:** `PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (the schema-derived sibling this
extends), `docs/design/IDEAL_TARGET_ARCHITECTURE.md` (canonical target arch),
`src/startd8/backend_codegen/` (the shipped schema-derived generator), the
`DeterministicFileProvider` registry (`contractors/deterministic_providers.py`).

> **Objective.** Add a **second class of deterministic generation** to the SDK: a
> **manifest-driven scaffold generator** that emits the project *plumbing* an app needs but
> which is **not derivable from the data contract** — async-task wiring, SQLite WAL/pragma
> config, file-logging setup, cold-start path, `Dockerfile`/compose, the Alembic baseline, and
> the FastAPI app-composition glue. This plumbing is boilerplate (no product judgment, no
> intelligence) yet today it is hand-authored or LLM-authored — the single largest remaining
> **non-deterministic surface that needs no LLM**. Driven by a small declared `app.yaml`
> manifest, it is `$0` LLM, drift-checked, build-gated, and registered as an owned-file
> provider exactly like `backend_codegen`.

> **Why now.** `backend_codegen` deterministically projects the *schema-derived* spine
> (models, tables, CRUD, templates, AI-pass scaffold). Analysis of the strtd8 MVP-1 plan shows
> the schema-derived spine reaches ~73% of the codebase; the gap between that and the ~84%
> achievable ceiling is **exactly this plumbing class** — repeated, derivable-from-a-manifest,
> and currently leaking to the LLM path. This generator closes that gap.

---

## 1. Problem Statement

There are **two distinct classes** of "derivable" code, and the SDK only generates one:

1. **Schema-derived** — everything projectable from `schema.prisma` (models, tables, CRUD,
   HTMX templates, AI edge schemas, completeness, export). Shipped: `backend_codegen/`.
2. **Manifest-derived plumbing** — boilerplate that is *not* a function of the schema but is
   equally un-intelligent: it is a function of a few project-level choices (which DB, async
   pattern, log path, container base). Examples from the strtd8 MVP-1 plan currently marked
   "LLM" or "glue": the async-AI `BackgroundTasks` + HTMX-polling pattern (R2-S8), SQLite WAL +
   `busy_timeout` (R3-S2), rotating file logging (R3-S3), the cold-start / empty-DB-no-key path
   (R4-S6), `Dockerfile`/compose, and the Alembic baseline + migration-on-contract-change
   (R2-S7, currently a `t-migrations` **LLM** task even though `alembic revision --autogenerate`
   is itself deterministic).

Class 2 is repeated across every project the SDK builds, needs no LLM, and is invention-prone
when an LLM writes it (it is exactly the "glue the model improvises" surface). It has no
generator today, so it falls through to the LLM path — inflating cost and re-introducing the
RUN-015/016/017 invention classes in the plumbing layer.

The decoupling seam already exists and is language- and source-agnostic: the
`DeterministicFileProvider` registry and the Phase-0.6 owned-file skip-hook. What is missing is
a **provider whose source-of-truth is a manifest rather than a schema**.

---

## 2. Scope

**In scope (v1):** a manifest (`app.yaml`) → a set of owned plumbing files for the
**all-Python FastAPI + SQLModel + HTMX** target; an owned-file provider; a `generate scaffold`
CLI subcommand; drift/`--check`; the Python build gate; the determinism-metric stamp.

**Out of scope (v1):** non-Python targets (Go/Java/C# scaffolds — future); inferring the
manifest from the schema or from prose (the manifest is hand-authored, small, and explicit —
same discipline as `schema.prisma`); deploy/runtime orchestration; any LLM call.

---

## 3. Functional Requirements

### Input contract

- **REQ-SCAF-1 Manifest is the source of truth.** A single hand-authored `app.yaml` declares
  the project-level choices the plumbing is a function of. It is small, explicit, and strictly
  parsed (malformed input raises immediately — never a silent LLM fallback, mirroring
  `backend_codegen`'s manifest discipline). v1 fields (all optional with lean defaults):
  ```yaml
  app:
    name: startd8
    package: app                 # python package root for emitted files
  persistence:
    backend: sqlite              # sqlite | (future: postgres)
    path: ./data/startd8.db
    wal: true                    # emit WAL + busy_timeout pragmas
    busy_timeout_ms: 5000
  migrations:
    tool: alembic                # alembic | none
  ai:
    async_pattern: background_polling   # background_polling | sse | none
    poll_interval_ms: 750
    timeout_s: 60
  logging:
    file: ./data/logs/startd8.log
    rotating: true
  cold_start:
    enabled: true                # emit empty-DB / no-key bootstrap path
  container:
    dockerfile: true
    compose: false
  ```

- **REQ-SCAF-2 Manifest is checkable and minimal.** Every field has a documented default so an
  empty `app.yaml` yields a runnable default scaffold. The manifest schema is versioned
  (`schema_version`) so the hash inputs are stable.

### Owned scaffold kinds (all $0 LLM, string-templated, byte-identical)

- **REQ-SCAF-3** The generator emits the following **owned kinds**, each carrying the standard
  `# startd8-artifact: <kind>` provenance header + content hash (over the *manifest* inputs, not
  the schema):

  | Kind | Artifact | Driven by |
  |------|----------|-----------|
  | `scaffold-db-config` | DB engine pragmas — WAL, `busy_timeout`, `get_session` tuning | `persistence` |
  | `scaffold-logging` | rotating file-logging setup module | `logging` |
  | `scaffold-async-ai` | async-AI pattern: background task runner + HTMX polling partial route(s) + per-call timeout | `ai.async_pattern` |
  | `scaffold-cold-start` | empty-DB / no-API-key bootstrap path (`init_db` invocation + "add your key" affordance hook) | `cold_start` |
  | `scaffold-alembic` | Alembic baseline (`alembic.ini`, `env.py`, initial revision) + a regenerate-on-contract-change runbook stub | `migrations` |
  | `scaffold-container` | `Dockerfile` (+ optional `compose.yaml`) | `container` |
  | `scaffold-app-compose` | top-level app-composition glue that wires the above into the `backend_codegen` `main.py`/`server.py` without editing those owned files | all |

- **REQ-SCAF-4 File-granular owned/authored seam (inherits R2-S9).** Every scaffold kind lives
  in its **own file**, separate from both hand-authored code and `backend_codegen` output, so
  the per-file skip-hook never false-drifts a mixed file. The app-composition kind
  (`scaffold-app-compose`) imports the owned spine; it never edits `backend_codegen`'s files.

### Determinism guarantees (inherited from shipped machinery)

- **REQ-SCAF-5 Byte-identical re-render (inherits R2-S4).** Re-rendering an in-sync scaffold
  file from the same manifest is byte-identical (pinned formatting, stable key/import order —
  no `black`/`ruff`/`isort` at emit time). Proven by a generate-twice → assert-identical test,
  not assumed.

- **REQ-SCAF-6 Drift / `--check` (reuse `drift.py` as-is).** `generate scaffold --check`
  re-renders and byte-compares; in-sync ⇒ `$0.00 GENERATED`; drift ⇒ exit non-zero. A
  stale/tampered scaffold file falls through to the LLM (safe failure), never a silent pass.

- **REQ-SCAF-7 Build-gated (reuse `validators/python_toolchain.py`).** Every emitted scaffold
  artifact passes `compileall` → `mypy` → `pytest`; an absent toolchain is non-pass, never a
  silent PASS (NFR-10 parity).

### Integration

- **REQ-SCAF-8 Registered owned provider.** A `ScaffoldFileProvider` (mirroring
  `PydanticSQLModelProvider`) registers under the existing entry-point group
  `startd8.contractors.deterministic_providers`. Its `owns()` recognizes the scaffold provenance
  header; `is_in_sync()` re-renders from the `app.yaml` resolved via `ProviderContext`
  source-anchors (suffix-matched `app.yaml`, fallback conventional path), exactly as the backend
  provider resolves `schema.prisma`. **No core changes** to `deterministic_providers.py` or the
  Phase-0.6 skip-hook are required — the registry is already polyglot.

- **REQ-SCAF-9 Standalone CLI (mirror `generate backend`).** One new
  `@generate_app.command("scaffold")` in `cli_generate.py`:
  `startd8 generate scaffold --manifest app.yaml --out . [--check] [--strict]`. Zero changes to
  `cli.py`. It is **not** an LLM pass.

- **REQ-SCAF-10 Anchored against `--fresh` wipe (inherits NFR-9 anchor-floor).** Emitted
  scaffold files and `app.yaml` are added to `.cap-dev-pipe/upstream-anchors.txt` so a
  `--fresh` contractor run cannot delete them and the skip-hook can resolve the manifest.

- **REQ-SCAF-11 Determinism-metric participation.** Because scaffold files are served via the
  registered provider, the Phase-0.6 skip-hook stamps `generation_path="deterministic_provider"`
  on those features, so the wired `DeterminismMetrics` (REQ-DET-METRIC) counts scaffold output
  in the measured `$0` fraction with no extra work. (Optionally a distinct `generation_path`
  value `"scaffold_provider"` may be used to split schema-derived vs manifest-derived
  contributions in `by_path`.)

---

## 4. Non-Functional Requirements

- **NFR-SCAF-1 Net-new, isolated.** New module `src/startd8/scaffold_codegen/` (renderers +
  `provider.py` + `manifest.py`), reusing `_headers`, `drift`, `python_toolchain`, and the
  skeleton dir-planning helpers as-is. **Zero changes** to `backend_codegen/` or the shipped TS
  path. Estimated ~400–600 LOC across the renderers + provider.
- **NFR-SCAF-2 Loud failure.** A malformed/unknown manifest field raises; an unsupported
  `persistence.backend`/`async_pattern` is an error, never an improvised emit.
- **NFR-SCAF-3 Composable with `backend_codegen`.** A project runs `generate backend` then
  `generate scaffold` (order-independent for emission; `scaffold-app-compose` imports spine
  symbols by their canonical owned paths). Together they cover schema-derived + plumbing.

---

## 5. Acceptance

- An `app.yaml` with WAL + alembic + background_polling + logging + cold-start emits the seven
  owned kinds; `compileall`/`mypy` pass; a second render is byte-identical and `--check` reports
  in-sync `$0.00`.
- A prime-contractor run whose `app.yaml` + scaffold files are on disk and in-sync **skips the
  LLM** for those features (Phase 0.6) and the postmortem's `DeterminismMetrics.file_ratio`
  rises by the scaffold file count.
- Deleting `data/startd8.db` and unsetting the API key, the emitted cold-start path boots,
  creates the schema, and reaches manual-entry state (satisfies strtd8 R4-S6 deterministically).
- `t-migrations` (strtd8 PLAN §7) is reclassified from **LLM** to **Owned** — the Alembic
  baseline is emitted by `scaffold-alembic`, not authored by a model.

---

## 6. Non-Goals

- No inference of `app.yaml` from the schema or prose (manifest is authored, like the contract).
- No runtime/deploy orchestration; the container artifacts are build inputs only.
- No non-Python scaffolds in v1.
- No LLM call anywhere in this path.

---

## 7. Open Questions

- **OQ-SCAF-1** Split `generation_path` value (`"scaffold_provider"`) vs reuse
  `"deterministic_provider"` — does the determinism metric benefit from distinguishing
  schema-derived from manifest-derived `$0` output? (Lean: split, for honest attribution.)
- **OQ-SCAF-2** Does `scaffold-alembic` emit only the baseline, or also wrap
  `alembic revision --autogenerate` as an owned, drift-checked step on contract change? (Lean:
  baseline owned in v1; the autogenerate wrapper is a fast follow — it is deterministic but
  touches a populated DB, so it needs the migration-preserves-rows test from strtd8 R2-S7.)
- **OQ-SCAF-3** Should `generate backend` and `generate scaffold` be unifiable under one
  `generate app --manifest app.yaml --schema schema.prisma` that runs both? (Lean: keep
  separate CLIs in v1 for a clean owned/owned seam; a convenience wrapper is cheap later.)
- **OQ-SCAF-4** Plan-ingestion awareness: should ingestion auto-emit an `app.yaml` + a
  `generate scaffold` prerequisite task so the scaffold files exist before Phase 0.6 runs?
  (See the plan-ingestion determinism-awareness recommendations — P2 there.)
