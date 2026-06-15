# Health-Endpoint Feature Benchmark (Informal) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-15
**Status:** Reshaped by planning; ready for CRP / M0 (grader, no spend)
**Owner:** SDK / Summer 2026 Benchmark (informal addendum)
**Relation:** Meta-experiment over `docs/design/health-endpoint/` (Requirements v0.2 + Plan v1.0).
**Paired plan:** `HEALTH_FEATURE_BENCH_PLAN.md` v1.0.

---

## 0. Planning Insights (Self-Reflective Update)

> Planning against the real PrimeContractor + grader code reshaped this experiment. The headline: the
> v0.1 framing was **infeasible** — it would have failed for every model for a reason unrelated to model
> skill. Catching that at doc cost (not after a paid run) is the loop working.

| v0.1 assumption | Planning discovery (evidence) | Impact |
|-----------------|-------------------------------|--------|
| Models implement the real backend_codegen change (edit 4 files + create 1) | **PC in benchmark-mode is a whole-file generator with NO surgical edit** — a feature on an existing file is whole-overwritten, then the size-regression guard blocks it → skipped/FAILED (`integration_engine.py:2965-3180`; micro-prime forced OFF `run_prime_workflow.py:385-386`). Round3 cells target exactly **one** new file (`seed-cartservice.json:33-35`). | **GO/NO-GO resolved: GO only via reframe.** Each cell = ONE new file; the model never edits existing files |
| The model wires the feature in (registration + mount) | Those are mechanical 1-liners → the **harness applies them deterministically**; the model writes only the substantive file | Isolates model *design* skill from plumbing; sidesteps the edit-incapability entirely |
| One experiment shape | Two natural single-file shapes: **Tier A** = `app/health.py` (the endpoint), **Tier B** = `health_renderer.py` (the SDK renderer) | Tier A is cheap/direct (run all 9); Tier B is the richer SDK-feature version (cost-gated) |
| Closed-loop deploy needs `--editable` (OQ-7) | A fresh minimal generated app has **no `startd8` runtime dep** → no `--editable`; only Tier B's *generate* step needs the model's SDK, via `PYTHONPATH=<sandbox>/src python -m startd8` | OQ-7 mostly mooted |
| Grader is new infra | Grade = `deploy_app_local()` → `stages['health'].reason` (`pass:app-health`/`pass:liveness-only`), already the exact signal; cost/quality free from `extract_metrics`; compile-gate = `python_toolchain.run_project_check` | Grader is a **thin script** |
| Need to build a test schema | `tests/fixtures/wireframe/prisma/schema.prisma` (3 models, relation, enum, list+create) exists | Reuse it |

**Quick wins / functional low-hanging fruit surfaced by planning:**
- **Two free, sharp discriminators** fall straight out of the health spec's own subtle traps:
  (1) **bare-`/health` vs prefix-router** — a model using `APIRouter(prefix="/health")` with only
  `/ready` makes bare `/health` 404 → the harness *already* grades `liveness-only` (zero new code);
  (2) **503-on-DB-failure** — re-probe with `DATABASE_URL` unreachable; many models return a
  200-with-error-body (we nearly did) → a one-probe discriminator.
- **Validate the grader for free** with non-LLM **control + negative** cells before any model spend.
- **Cost/quality is free** from `compare-models` (`extract_metrics`); the grader only adds the runtime grade.
- **The grader is generic** — "generate one file → place → runtime-probe → grade" — reusable for any
  future informal single-feature benchmark, not health-specific.

**Resolved open questions:**
- **OQ-1 → Reframe to single-new-file cells.** PC cannot edit existing files in benchmark-mode; the
  harness does the deterministic wiring. (This is the go/no-go: GO, only reframed.)
- **OQ-2 → Source root by tier.** Tier A = a small pre-generated wireframe app (fast sandbox); Tier B =
  a clean pre-health SDK checkout. NOT a full SDK the model edits.
- **OQ-3 → Thin grader** reusing `deploy_app_local` + `extract_metrics` + `run_project_check`; mirrors
  `deploy_harness/batch.py`.
- **OQ-4 → `tests/fixtures/wireframe/prisma/schema.prisma`** (has list+create → smoke-exercisable).
- **OQ-5 → Reps:** Tier A cheap → 3 reps for flagships; Tier B → 1 rep.
- **OQ-6 → Budget:** Tier A trivial (run all 9); Tier B flagship ≈ 3×$3, gate the other 6.
- **OQ-7 → No `--editable` for the deploy** (generated app is standalone); Tier B's generate step uses
  `PYTHONPATH=<sandbox>/src`.

---

## 1. Problem Statement

We just authored a complete spec for the generated-app `/health` endpoint (requirements v0.2 + plan
v1.0). That spec is itself a well-scoped SDK code-generation task. **Informal experiment:** feed that
spec back through the **Prime Contractor** workflow across multiple models and see which models can
*implement the SDK feature* from the spec — graded by the **deploy harness** we built (does the
resulting `generate backend` emit a `/health` that reaches `pass:app-health`?).

This is a self-referential benchmark — the SDK building a piece of itself — and a real-world signal of
"can model X turn our spec into working SDK code?" It is **informal**: not part of the formal round3
microservices matrix, indicative not statistical.

| Component | Current state | Gap |
|-----------|---------------|-----|
| Health spec | req v0.2 + plan v1.0 exist | Not yet implemented by anyone |
| Model comparison | `model_comparison.py` / `compare-models` runs app-build seeds | No seed for an SDK-feature task; no closed-loop feature grader |
| Grading | round3 = compile_gate + disk_quality | No "does the feature actually work" signal |
| Deploy harness | grades generated *apps* | Not yet wired to grade an SDK *feature* implementation |

---

## 2. Goals & Non-Goals

**Goals**
- Turn the health spec into a Prime Contractor seed and run it across models in isolated sandboxes.
- Grade each model's implementation with a **closed loop**: apply → `generate backend` → `deploy local`
  → did `/health` reach `pass:app-health` (without regressing boot/smoke)?
- Compare models on this real SDK-feature task, joined with cost; flagship-first, cost-gated.

**Non-Goals**
- NOT part of formal round3; informal, indicative, clearly labeled.
- NOT statistical (low reps).
- Does NOT auto-merge any model's implementation — the human reviews the winner before adopting.
- Does NOT change the formal benchmark scoring formula.

---

## 3. Requirements

### Cell shape (the reframe)
- **FR-1** Each benchmark **cell is a single-new-file task** (parity with round3's one-`target_files`
  design). The model **never edits an existing file**; the harness applies all mechanical wiring
  deterministically. Two tiers:
  - **FR-1a (Tier A — endpoint):** the model generates **`app/health.py`** — a FastAPI `health_router`
    with `GET /health` (readiness: `SELECT 1` via the app's `get_session`; `200 {"status":"ok"}` /
    `503 {"status":"degraded","checks":{"db":"down"}}`) and `GET /health/live` (`200 {"status":"alive"}`).
  - **FR-1b (Tier B — SDK renderer):** the model generates **`backend_codegen/health_renderer.py`** with a
    **pinned signature** `render_health(schema_text, source_file) -> str` returning deterministic
    `app/health.py` source (self-embedded header `# startd8-artifact: fastapi-health` + `schema-sha256`).
- **FR-2** **Source root by tier:** Tier A = a small pre-generated wireframe app *without* health (so
  `app/db.py` exists for the import surface); Tier B = a **clean SDK checkout at a pinned pre-health SHA**.
  Record the SHA / fixture hash. (NOT a full SDK the model edits — that's infeasible, see §0.)
- **FR-3** Build the **seed** from health req v0.2 + plan v1.0: `task_description` + `requirements_text`
  carrying the normative 200/503 contract, the **bare-`/health` constraint**, the readiness=`SELECT 1`
  rule, and (Tier B) the pinned `render_health` signature + owned-artifact header conventions.
  `language: python`, one `target_files` entry. Pin + hash like round3 seeds.

### Orchestration
- **FR-4** Run via **`compare-models` / `model_comparison.py`**: serial, isolated sandboxes, model
  pinned (lead+drafter), `--force-regenerate`, `--benchmark-mode` (micro-prime OFF), round3 parity.
- **FR-5** **Models & cost:** **Tier A** is trivially cheap (one small file) → run **all 9** models, 3
  reps for the 3 flagships. **Tier B** → **3 flagship first** (`anthropic:claude-opus-4-8`,
  `openai:gpt-5.5`, `gemini:gemini-2.5-pro`) at a **$3/cell cap**; after observing cost, **gate the
  other 6** on a recorded decision.

### Grader (thin, generic, validated-first)
- **FR-6** The grader is a **thin script reusing existing pieces** — `deploy_app_local()` (health grade),
  `extract_metrics()` (free cost/quality), `run_project_check()` (compile-gate) — NOT `deploy_batch`.
  It is **generic**: "place one generated file → apply deterministic wiring → runtime-probe → grade",
  reusable for future single-feature informal benchmarks.
- **FR-7** Per cell the grader runs: (a) **compile-gate**; (b) **deterministic wiring** — Tier A: append
  the mount to `app/main.py`; Tier B: apply the 4 registration 1-liners + run `generate backend` via
  `PYTHONPATH=<sandbox>/src` against the wireframe schema; (c) **(Tier B) drift** — `generate backend
  --check` → expect **in_sync** (correct header/sha/determinism = an SDK-convention discriminator);
  (d) **deploy** `deploy_app_local(app_root)` (no `--editable`; the app is standalone); (e) **grade** the
  health rung: `pass:app-health` vs `pass:liveness-only` vs `fail`.
- **FR-8** **Two discriminator probes** (the sharp, free signals): (1) the harness's existing
  `app-health` vs `liveness-only` distinction catches the **bare-`/health` vs prefix-router** trap;
  (2) a **DB-down probe** — re-request `GET /health` with `DATABASE_URL` unreachable — expects **503**,
  failing any model that returns a 200-with-error-body.
- **FR-9** **Validate the grader before any model spend** with non-LLM cells: a **control** (the reference
  `app/health.py` → expect `app-health` + 503-correct), and **two negatives** (prefix-only → expect
  `liveness-only`; 200-on-failure → expect the 503 probe to fail). Keep them as regression fixtures.

### Reporting, cost governance, reproducibility
- **FR-10** Emit a per-model **graded ladder** + headline table: `generated → compiles →
  [Tier B: drift-recognized →] health-grade → 503-correct`, joined with the free cost/quality, **clearly
  labeled INFORMAL / indicative-not-statistical**, on a **separate batch root** from round3. The
  **control cell is the ceiling** for interpretation.
- **FR-11** Enforce a per-cell cap + total ceiling; record the Tier-A→Tier-B and flagship→other-6
  go/no-go decisions with the observed cost.
- **FR-12** Pin the source-root SHA/fixture hash, the test schema, and the seed hash; record
  `harness_env` per cell (mirrors the deploy-harness reproducibility discipline).

---

## 4. Non-Requirements

- Not formal-benchmark; not added to round3's matrix or scoring formula.
- Not statistical; reps kept low (cost).
- **Does NOT ask models to edit existing files** — infeasible in PC benchmark-mode (§0); single-new-file only.
- No auto-adoption of any model's file into the SDK; the human reviews the winner.
- No new orchestration engine — extends `model_comparison.py` + reuses the deploy harness only.
- Tier B does NOT require the model to author the registration wiring (the harness does it deterministically).

---

## 5. Open Questions

All seven v0.1 open questions were resolved by the planning pass — see §0 (Resolved open questions).
None block **M0** (build + validate the grader on the control/negative cells — *no model spend*).
Decisions settled: single-new-file cells, two tiers (A endpoint / B renderer), deterministic harness
wiring, thin validated grader, wireframe test schema, two free discriminators (bare-`/health`, 503),
Tier-A-all-9 then Tier-B-flagship-gated.

---

*v0.2 — Post-planning self-reflective update. The experiment was **reshaped, not tweaked**: the v0.1
core (models implement the SDK change by editing files) was infeasible in PC benchmark-mode and would
have failed for every model. Reframed to single-new-file cells + deterministic harness wiring + a thin
validated grader; added a two-tier design, two free discriminators, and a grader-validation gate. 3
requirements corrected (FR-1/2/3), 9 added/added-detail (FR-4..12), 7 open questions resolved. Paired
with HEALTH_FEATURE_BENCH_PLAN.md v1.0.*
