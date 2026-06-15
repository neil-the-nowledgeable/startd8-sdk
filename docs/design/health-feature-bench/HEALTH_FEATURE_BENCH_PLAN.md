# Health-Endpoint Feature Benchmark (Informal) — Implementation Plan

**Version:** 1.0 (paired with Requirements v0.2)
**Date:** 2026-06-15
**Status:** Planned — pre-implementation

---

## 0. Planning Discoveries (feed §0 of the requirements)

| v0.1 assumed | Planning revealed (evidence) | Impact |
|--------------|------------------------------|--------|
| Models implement the real backend_codegen change (edit 4 files + create 1) | **PC in benchmark-mode is a whole-file generator with NO surgical edit.** A feature on an existing file → whole overwrite → size-regression guard blocks → skipped/FAILED (`integration_engine.py:2965-3180`, `standalone.py:248-334`; micro-prime forced OFF `run_prime_workflow.py:385-386`) | **The drafted task is infeasible — every model would fail.** Reframe to single-new-file cells (§1) |
| A cell can target multiple files | Round3 cells target **one** `target_files` entry (`seed-cartservice.json:33-35`) | Each cell = ONE new file, parity with round3 |
| Models must edit `CANONICAL_LAYOUT`/`render_main`/`drift`/`assembler` | Those are mechanical 1-liners → the **harness applies them deterministically**; the model only writes the substantive new file | Isolates model *design* skill from plumbing; avoids OQ-1 by design |
| Need `--editable` for the closed-loop deploy (OQ-7) | A freshly generated minimal app has **no `startd8` runtime dep** → deploys with no `--editable`. Only Tier B's *generate* step needs the model's SDK, cleanly via `PYTHONPATH=<sandbox>/src python -m startd8 generate backend` (`cli_generate.py` relative import) | OQ-7 mostly mooted; generate-step shadowing is one env var |
| Grader is new infra | Grade = `deploy_app_local()` → `stages['health'].reason` (`pass:app-health` vs `pass:liveness-only`), already returns the exact signal (`deploy_harness/server.py` `_PROBES`); cost/quality free from `extract_metrics` (`model_comparison.py:230-275`); compile-gate = `validators/python_toolchain.run_project_check` | Grader is a **thin script**, not new infra |
| Need to build a test schema | `tests/fixtures/wireframe/prisma/schema.prisma` (3 models, relation, enum, list+create) already exists | OQ-4 resolved — reuse it |

These reshape the experiment (>>30% revision) and convert a moot run into a feasible, sharper one.

## 1. The reframe: single-new-file cells + deterministic harness wiring

The model **never edits an existing file**. Each cell asks the model to generate **one new file**; the
harness deterministically applies the (fixed, mechanical) wiring and grades the result. Two tiers:

- **Tier A — endpoint (`app/health.py`)** *(cheap, direct, run first):* the model writes the FastAPI
  health router itself. Source root = a pre-generated wireframe app *without* health (so `app/db.py` is
  present for the import surface). Harness adds the one mount line to `app/main.py` deterministically,
  deploys, grades. Purest measure of "can the model write a correct `/health`." ~1 small file → run **all 9**.
- **Tier B — SDK renderer (`backend_codegen/health_renderer.py`)** *(richer, cost-gated):* the model
  writes `render_health(schema_text, source_file) -> str` (signature **pinned in the seed** so the
  deterministic wiring can call it). Source root = a clean pre-health SDK checkout. Harness applies the 4
  registration 1-liners + mounts, runs `generate backend` with the model's SDK (`PYTHONPATH=<sandbox>/src`),
  deploys the emitted app, grades. Adds an SDK-convention discriminator: does `generate backend --check`
  report the model's artifact **in_sync** (correct header + schema-sha + determinism)?

## 2. The grader (thin, generic, validated first)

A `grade_cell(target_file, place_fn, generate_fn, probes) -> CellResult` reusing existing pieces:
1. **placement** — drop the model's file where it belongs (Tier A: `app/health.py`; Tier B: the renderer).
2. **deterministic wiring** — Tier A: append the mount to `main.py`; Tier B: apply the 4 registration
   edits + run `generate backend` via `PYTHONPATH=<sandbox>/src` against the wireframe schema.
3. **compile-gate** — `run_project_check(project, run_mypy=False, run_pytest=False)`.
4. **(Tier B) drift** — `generate backend --check` → expect `in_sync` (SDK-convention adherence).
5. **deploy + grade** — `deploy_app_local(app_root)` → read `stages['health']`:
   `pass:app-health` (real `/health` 200) vs `pass:liveness-only` (only `/openapi.json`) vs `fail`.
6. **503 discriminator** — re-probe `GET /health` with `DATABASE_URL` pointed at an unreachable DB;
   expect **503**, not a 200-with-error-body.

**Validate the grader before any model spend** with non-LLM cells:
- **Control** = our reference `app/health.py` → expect `app-health` + 503-correct (proves it passes good code).
- **Negative-1** = `prefix="/health"`-only router (bare `/health` 404s) → expect `liveness-only`
  (proves the bare-path discriminator fires).
- **Negative-2** = 200-on-DB-failure → expect the 503 probe to FAIL (proves the fail-closed discriminator).
If the grader doesn't reproduce these, fix the grader first — don't trust it on models.

## 3. Orchestration

- Tier A & B both run via **`compare-models` / `model_comparison.py`** (serial, isolated sandboxes,
  model pinned, `--force-regenerate`, `--benchmark-mode`) with a **single-task seed** (one `target_files`).
- Tier A source root = a tiny pre-generated wireframe app (fast to sandbox). Tier B = clean SDK checkout
  at a pinned pre-health SHA.
- A post-run grader script walks the per-model sandboxes (mirrors `deploy_harness/batch.py`), runs §2,
  and joins with the free `extract_metrics` cost/quality into a report on a **separate informal batch root**.

## 4. Cost & sequencing

- **M0** — build + validate the grader on the 3 non-LLM cells (control + 2 negatives). No model spend.
- **M1 — Tier A, all 9 models** (one tiny file each; trivial cost; 3 reps for flagships affordable).
  Headline table: cost × {generated, compiles, health-grade, 503-correct}.
- **M2 — decision gate:** review Tier A cost/results → decide Tier B scope.
- **M3 — Tier B, 3 flagship first** ($3/cell cap), gate the other 6 on observed cost. Adds the
  drift-in_sync (SDK-convention) column.

## 5. Risks

- **Tier B deterministic wiring depends on the model's renderer exposing the pinned `render_health`
  signature** — if a model renames it, the `assembler` edit can't call it → that cell grades
  `generate-failed` (a legitimate "didn't follow the contract" outcome, recorded distinctly).
- **PC may still try to "helpfully" touch other files** even on a single-`target_files` seed — verify the
  cell only writes the one target; treat stray writes as a deviation.
- **Grader trust** — mitigated by the M0 control/negative validation gate (§2).
- **Cost creep on Tier B** — flagship-first gate (M2/M3).

## 6. Test plan

- Grader unit: control/negative fixtures produce the expected `app-health` / `liveness-only` / 503-fail
  grades (these ARE the M0 validation cells, kept as regression fixtures).
- One end-to-end dry run of the Tier-A seed through `compare-models` with a single cheap model
  (e.g. a flash/mini tier) to confirm the seed → sandbox → grade pipeline before the full M1.

## 7. Traceability

§0 resolves OQ-1..7. Every v0.2 FR maps to a step here; the reframe (single-new-file + deterministic
wiring + validated thin grader) is the spine. No open questions block M0 (grader, no spend).
