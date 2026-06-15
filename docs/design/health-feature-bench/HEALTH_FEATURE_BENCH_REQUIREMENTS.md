# Health-Endpoint Feature Benchmark (Informal) — Requirements

**Version:** 0.3 (Post-planning + capability re-investigation)
**Date:** 2026-06-15
**Status:** Corrected; ready for CRP / M0 (grader, no spend)
**Owner:** SDK / Summer 2026 Benchmark (informal addendum)
**Relation:** Meta-experiment over `docs/design/health-endpoint/` (Requirements v0.2 + Plan v1.0).
**Paired plan:** `HEALTH_FEATURE_BENCH_PLAN.md` v1.1.

---

## 0. Planning Insights (Self-Reflective Update)

> **⚠️ v0.2 correction (v0.3):** v0.2 claimed PrimeContractor *cannot* edit existing files in
> benchmark-mode and therefore reframed the whole experiment to single-new-file cells. **That was
> wrong** — it rested on a sub-agent summary, not the code. Re-reading the bytes: PC has a **first-class
> edit mode** (`context_seed/core.py:1506` `_classify_edit_mode`; `integration_engine.py:3125-3143`
> edit-mode whole-file copy with merge *deliberately* skipped — comment: *"edit-mode tasks where the
> staging file IS the complete file"*; plus the `_merge_subset_into_target` difflib splice at `2511`).
> Existing-file edits are **auto-classified** from on-disk existence (`scaffold.existing_target_files`,
> `existing_content_hash`) — no special seed annotation needed. The size-regression guard
> (`2979-3014`) is a *truncation* safety net (fires only when the new file is <60% of the original),
> overridable (`allow_size_regression` / per-file `size_regression_override`) with the splice as repair
> fallback — **not** a hard block. Round3's one-file-per-cell is a *benchmark design choice* (implement
> one service), not a capability limit.

| v0.1/v0.2 assumption | Re-investigation (evidence) | Impact |
|-----------------|-------------------------------|--------|
| (v0.2) PC can't edit existing files → must reframe to single-new-file | **FALSE.** PC edit-mode classifies existing targets as `edit` and copies the model's complete file (merge skipped); a difflib subset-splice handles additive partials; size guard is an overridable truncation net (`core.py:1506`, `integration_engine.py:2511,3125-3143,2979-3014`) | **The realistic multi-file-edit SDK-feature task is FEASIBLE** — restored as the PRIMARY experiment |
| (v0.1) Models implement the real backend_codegen change (edit 4 files + create 1) | Feasible. The model must return each edited file **complete** (its existing lines + the additions); editing a ~300-line file like `crud_generator.py` is a real *model-skill* challenge (truncation/content-drop, caught by the size guard) — a **measurable signal**, not an architectural block | Primary task = the real feature; the edit-skill itself becomes a discriminator |
| Single-file reframe is required | It is **optional**, not required — a cheaper/cleaner *variant* that isolates design skill from edit mechanics | Tiers retained as optional cost/signal-isolation variants, not a forced workaround |
| Closed-loop deploy needs `--editable` (OQ-7) | A fresh minimal generated app has **no `startd8` runtime dep** → no `--editable`; the *generate* step uses the model's SDK via `PYTHONPATH=<sandbox>/src python -m startd8` | OQ-7 mostly mooted |
| Grader is new infra | Grade = `deploy_app_local()` → `stages['health'].reason`; cost/quality free from `extract_metrics`; compile-gate = `python_toolchain.run_project_check` | Grader is a **thin script** |
| Need to build a test schema | `tests/fixtures/wireframe/prisma/schema.prisma` (3 models, relation, enum, list+create) exists | Reuse it |

**Quick wins / functional low-hanging fruit surfaced by planning:**
- **Two free, sharp discriminators** fall straight out of the health spec's own subtle traps:
  (1) **bare-`/health` vs prefix-router** — a model using `APIRouter(prefix="/health")` with only
  `/ready` makes bare `/health` 404 → the harness *already* grades `liveness-only` (zero new code);
  (2) **503-on-DB-failure** — re-probe with `DATABASE_URL` unreachable; many models return a
  200-with-error-body (we nearly did) → a one-probe discriminator.
- **Validate the grader for free** with non-LLM **control + negative** cells before any model spend.
- **Cost/quality is free** from `compare-models` (`extract_metrics`); the grader only adds the runtime grade.
- **The grader is generic** — "generate file(s) → apply/verify → runtime-probe → grade" — reusable for any
  future informal feature benchmark, not health-specific.
- **Edit-fidelity is itself a discriminator** (v0.3): the primary task requires editing a ~300-line file
  (`crud_generator.py`) while preserving its content. The size-regression guard + a diff of the model's
  edited file vs the original = a free measure of *content-preservation* (did the model drop existing
  code?). A sharp, realistic signal weak models fail.

**Resolved open questions:**
- **OQ-1 → GO, no reframe needed.** PC **can** edit existing files (edit-mode auto-classified from
  on-disk existence). The **primary** experiment is the realistic multi-file-edit SDK feature; the
  single-file tiers are an *optional* cheaper variant. (v0.2's "reframe required" was wrong — see ⚠️.)
- **OQ-2 → Source root.** Primary (multi-file edit) = a clean **SDK checkout at a pinned pre-health SHA**
  (the model edits the real `backend_codegen` files; edit-mode auto-classifies them). Optional Tier-A
  variant = a small pre-generated wireframe app.
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

### Cell shape (PC edits existing files — see §0)
- **FR-1 (PRIMARY — the real SDK feature):** Feed the **full health spec** (health plan v1.0 §1) as the
  task: the model implements the feature by **creating `backend_codegen/health_renderer.py` AND editing
  the existing files** (`crud_generator.py` `CANONICAL_LAYOUT` + `render_main` mount, `assembler.py`
  emit, `drift.py` `_renderers`, `test_emitter.py`). PC **auto-classifies** the existing targets as
  `edit` from on-disk existence; each must be returned **complete** (existing content + additions). This
  is the experiment the user asked for and it tests both *design* (the renderer) and *edit-fidelity*
  (preserving a ~300-line file) — the latter a sharp discriminator.
  - **Edit-mechanics knob:** decide per run whether to set `allow_size_regression` (lets a correct-but-
    partial edit through / triggers the splice) or leave it OFF to measure **raw full-file fidelity**.
    Default OFF (stricter, more discriminating); record the choice.
- **FR-1-ALT (OPTIONAL single-file variants — cheaper, cleaner signal):** if the primary task proves too
  noisy or costly, fall back to single-new-file cells where the harness applies the mechanical wiring:
  *Variant A* = model writes only `app/health.py` (the endpoint); *Variant B* = model writes only
  `health_renderer.py` (pinned signature `render_health(schema_text, source_file) -> str`). These isolate
  design skill from edit mechanics. **Not required** — a deliberate simplification, not a workaround.
- **FR-2** **Source root:** primary = a **clean SDK checkout at a pinned pre-health SHA** (so the produced
  diff *is* the feature and edit-mode auto-classifies the real files); record the SHA. Optional Variant A
  uses a small pre-generated wireframe app.
- **FR-3** Build the **seed** from health req v0.2 + plan v1.0: `task_description` + `requirements_text`
  carrying the normative 200/503 contract, the **bare-`/health` constraint**, readiness=`SELECT 1`, the
  files-touched list + pinned `render_health` signature + owned-artifact header conventions. `language:
  python`. Pin + hash like round3 seeds. (Multi-`target_files` for the primary task; one for a variant.)

### Orchestration
- **FR-4** Run via **`compare-models` / `model_comparison.py`**: serial, isolated sandboxes, model
  pinned (lead+drafter), `--force-regenerate`, `--benchmark-mode` (micro-prime OFF), round3 parity.
- **FR-5** **Models & cost:** **3 flagship first** (`anthropic:claude-opus-4-8`, `openai:gpt-5.5`,
  `gemini:gemini-2.5-pro`) at a **$3/cell cap**; after observing cost, **gate the other 6** on a recorded
  decision (per the user's framing). (If a cheap single-file *variant* is run, it can include all 9.)

### Grader (thin, generic, validated-first)
- **FR-6** The grader is a **thin script reusing existing pieces** — `deploy_app_local()` (health grade),
  `extract_metrics()` (free cost/quality), `run_project_check()` (compile-gate) — NOT `deploy_batch`.
  It is **generic**: "take the model's modified SDK → run `generate backend` → runtime-probe → grade",
  reusable for future single-feature informal benchmarks.
- **FR-7** Per cell the grader runs against the model's sandbox SDK: (a) **compile-gate** the modified
  SDK (`run_project_check`); (b) **edit-fidelity** — diff each edited file vs the pre-health original;
  record content-preservation (did the model drop existing code? size-regression flagged?); (c)
  **`generate backend --check`** → expect **in_sync** (correct header/sha/determinism — an SDK-convention
  discriminator); (d) **`generate backend`** on the wireframe schema via `PYTHONPATH=<sandbox>/src python
  -m startd8` → emits `app/health.py` + the mount; (e) **deploy** `deploy_app_local(app_root)` (no
  `--editable`; the generated app is standalone); (f) **grade** the health rung: `pass:app-health` vs
  `pass:liveness-only` vs `fail`. *(For an optional single-file variant, the harness applies the
  mechanical wiring in place of the model's edits at step (b)/(d).)*
- **FR-8** **Two discriminator probes** (the sharp, free signals): (1) the harness's existing
  `app-health` vs `liveness-only` distinction catches the **bare-`/health` vs prefix-router** trap;
  (2) a **DB-down probe** — re-request `GET /health` with `DATABASE_URL` unreachable — expects **503**,
  failing any model that returns a 200-with-error-body.
- **FR-9** **Validate the grader before any model spend** with non-LLM cells: a **control** (the reference
  `app/health.py` → expect `app-health` + 503-correct), and **two negatives** (prefix-only → expect
  `liveness-only`; 200-on-failure → expect the 503 probe to fail). Keep them as regression fixtures.

### Reporting, cost governance, reproducibility
- **FR-10** Emit a per-model **graded ladder** + headline table: `generated → compiles → edit-fidelity
  (content preserved) → drift-recognized → health-grade → 503-correct`, joined with the free
  cost/quality, **clearly labeled INFORMAL / indicative-not-statistical**, on a **separate batch root**
  from round3. The **control cell is the ceiling** for interpretation.
- **FR-11** Enforce a per-cell cap + total ceiling; record the Tier-A→Tier-B and flagship→other-6
  go/no-go decisions with the observed cost.
- **FR-12** Pin the source-root SHA/fixture hash, the test schema, and the seed hash; record
  `harness_env` per cell (mirrors the deploy-harness reproducibility discipline).

---

## 4. Non-Requirements

- Not formal-benchmark; not added to round3's matrix or scoring formula.
- Not statistical; reps kept low (cost).
- No auto-adoption of any model's diff into the SDK; the human reviews the winner.
- No new orchestration engine — extends `model_comparison.py` + reuses the deploy harness only.
- Does NOT require a single-file reframe — PC edits existing files (§0); the multi-file feature is the
  primary task, single-file variants are optional.

---

## 5. Open Questions

All seven v0.1 open questions are resolved (see §0). None block **M0** (build + validate the grader on
the control/negative cells — *no model spend*). The one residual *design choice* (not a blocker): the
edit-mechanics knob (`allow_size_regression` ON vs OFF) — default OFF to measure raw full-file fidelity;
revisit if too many cells fail on benign partial edits.

---

*v0.3 — Corrected v0.2's central error. v0.2 wrongly concluded (from a sub-agent summary, not the code)
that PC cannot edit existing files, and over-reframed to single-file-only. Re-reading the bytes
(`context_seed/core.py:1506`, `integration_engine.py:2511,3125-3143,2979-3014`) shows PC has a
first-class **edit mode** auto-classified from on-disk existence. The realistic multi-file-edit SDK
feature is **restored as the primary experiment**; single-file cells demoted to optional cheaper
variants. Added edit-fidelity as a discriminator + the size-regression knob. Lesson: read the code,
not the summary, before declaring something infeasible. Paired with HEALTH_FEATURE_BENCH_PLAN.md v1.1.*
