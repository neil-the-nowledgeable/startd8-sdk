# Health-Endpoint Feature Benchmark (Informal) — Implementation Plan

**Version:** 1.1 (paired with Requirements v0.3)
**Date:** 2026-06-15
**Status:** Planned — pre-implementation

> **v1.1 correction:** v1.0 claimed PC can't edit existing files and built the plan around a
> single-new-file reframe. **Wrong** — PC has a first-class edit mode (see §0). The plan below is
> corrected: the **primary** path is the realistic multi-file-edit SDK feature; single-file cells are an
> optional cheaper variant.

---

## 0. Planning Discoveries (feed §0 of the requirements)

| assumption | re-investigation (evidence) | Impact |
|--------------|------------------------------|--------|
| (v1.0) PC is a whole-file generator with NO surgical edit → reframe to single-new-file | **FALSE.** PC has first-class **edit mode**: `_classify_edit_mode` auto-detects existing targets (`context_seed/core.py:1506`); edit-mode copies the model's *complete* file with merge deliberately skipped (`integration_engine.py:3125-3143`); a difflib subset-splice handles additive partials (`2511`); the size-regression guard fires only on <60% truncation and is overridable (`2979-3014`) | **Multi-file-edit SDK feature is FEASIBLE** → restored as the primary experiment |
| Round3 one-file-per-cell ⇒ PC can't do multi-file | That's a *benchmark design choice* (one Online Boutique service per cell), not a capability limit | Multi-`target_files` tasks are fine |
| The model must edit the registration files | Yes — and editing a ~300-line file (`crud_generator.py`) intact is a real **model-skill discriminator**; the size-regression guard + a content diff measure it for free | Edit-fidelity becomes a graded column |
| Need `--editable` for the closed-loop deploy (OQ-7) | A freshly generated minimal app has **no `startd8` runtime dep** → deploys with no `--editable`. The *generate* step uses the model's SDK via `PYTHONPATH=<sandbox>/src python -m startd8 generate backend` | OQ-7 mostly mooted |
| Grader is new infra | Grade = `deploy_app_local()` → `stages['health'].reason`; cost/quality free from `extract_metrics`; compile-gate = `validators/python_toolchain.run_project_check` | Grader is a **thin script** |
| Need to build a test schema | `tests/fixtures/wireframe/prisma/schema.prisma` exists | OQ-4 resolved — reuse it |

## 1. The experiment: the real multi-file SDK feature (primary) + optional single-file variants

**Primary — implement the actual feature.** Each model's cell is the **full health spec** (health plan
v1.0 §1): create `backend_codegen/health_renderer.py` AND edit `crud_generator.py` (CANONICAL_LAYOUT +
render_main mount), `assembler.py`, `drift.py`, `test_emitter.py`. PC auto-classifies the existing files
as `edit`; the model must return each **complete**. Source root = a clean SDK checkout at a pinned
pre-health SHA. This tests *design* (the renderer) AND *edit-fidelity* (preserving large files) — both
real discriminators. **Edit-mechanics knob:** default `allow_size_regression` OFF (measures raw
full-file fidelity); flip ON only if benign partial edits are being blocked too often.

**Optional variants (cheaper / cleaner signal, only if the primary is too noisy or costly):** single-new
-file cells where the *harness* applies the mechanical wiring — *Variant A* = `app/health.py` (endpoint),
*Variant B* = `health_renderer.py` (pinned `render_health` signature). Not required.

## 2. The grader (thin, generic, validated first)

A `grade_cell(model_sandbox) -> CellResult` reusing existing pieces, run against the model's modified SDK:
1. **compile-gate** — `run_project_check(model_sandbox, run_mypy=False, run_pytest=False)` on the edited SDK.
2. **edit-fidelity** — diff each edited file (`crud_generator.py`, `assembler.py`, `drift.py`,
   `test_emitter.py`) vs the pre-health original; record content preserved / size-regression flagged.
3. **drift** — `PYTHONPATH=<sandbox>/src python -m startd8 generate backend --check` (after a generate)
   → expect `in_sync` (correct header/sha/determinism — SDK-convention adherence).
4. **generate** — `PYTHONPATH=<sandbox>/src python -m startd8 generate backend --schema <wireframe> --out <app>`
   → the model's renderer emits `app/health.py` + the mount.
5. **deploy + grade** — `deploy_app_local(app)` → read `stages['health']`: `pass:app-health` (real
   `/health` 200) vs `pass:liveness-only` (only `/openapi.json`) vs `fail`. No `--editable` (app is standalone).
6. **503 discriminator** — re-probe `GET /health` with `DATABASE_URL` unreachable; expect **503**, not 200.

*(For an optional single-file variant, replace steps 1-4 with: place the model's one file into a known-
good scaffold and let the harness apply the mechanical wiring.)*

**Validate the grader before any model spend** with non-LLM cells (place a hand-written file into the
scaffold; the grader must reproduce the expected grade):
- **Control** = the reference `health.py` → expect `app-health` + 503-correct (proves it passes good code).
- **Negative-1** = `prefix="/health"`-only router (bare `/health` 404s) → expect `liveness-only`.
- **Negative-2** = 200-on-DB-failure → expect the 503 probe to FAIL.
If the grader doesn't reproduce these, fix the grader first — don't trust it on models.

## 3. Orchestration

- Run via **`compare-models` / `model_comparison.py`** (serial, isolated sandboxes, model pinned,
  `--force-regenerate`, `--benchmark-mode`). Primary seed = multi-`target_files` (the feature); source
  root = a clean SDK checkout at the pinned pre-health SHA (edit-mode auto-classifies the real files).
- A post-run grader script walks the per-model sandboxes (mirrors `deploy_harness/batch.py`), runs §2,
  and joins with the free `extract_metrics` cost/quality into a report on a **separate informal batch root**.

## 4. Cost & sequencing

- **M0** — build + validate the grader on the 3 non-LLM cells (control + 2 negatives). No model spend.
- **M1 — primary task, 3 flagship first** ($3/cell cap): each implements the real multi-file feature.
  Headline table: cost × {generated, compiles, edit-fidelity, drift-in_sync, health-grade, 503-correct}.
- **M2 — decision gate:** review flagship cost/results → decide the other-6 scope (and whether the
  primary is too noisy → run an optional single-file variant instead).
- **M3 — other 6** (if the gate says go), and/or the optional cheaper single-file variant for breadth.

## 5. Risks

- **Editing a ~300-line file with content-drop** — the central model-skill risk; the size-regression
  guard (default ON-as-block) catches gross truncation, and the edit-fidelity diff measures it. A cell
  that drops content grades low — a legitimate, informative outcome.
- **A model renames the pinned `render_health` signature** — the deterministic generate step (or the
  assembler edit) can't resolve it → `generate-failed` (a real "didn't follow the contract" signal).
- **PC stray writes** — verify the cell only touches the intended files; treat extras as deviations.
- **Grader trust** — mitigated by the M0 control/negative validation gate (§2).
- **Cost** — flagship-first gate (M2).

## 6. Test plan

- Grader unit: control/negative fixtures produce the expected `app-health` / `liveness-only` / 503-fail
  grades (these ARE the M0 validation cells, kept as regression fixtures).
- One end-to-end dry run of the primary seed through `compare-models` with a single cheap model
  (e.g. a flash/mini tier) to confirm the seed → sandbox → edit → generate → grade pipeline before M1.

## 7. Traceability

§0 resolves OQ-1..7. Every v0.3 FR maps to a step here; the spine is the real multi-file SDK feature +
validated thin grader, with single-file variants optional. No open questions block M0 (grader, no spend).
