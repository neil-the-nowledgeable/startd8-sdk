# Multi-Phase Judging — Readily-Judgeable Outputs (Requirements)

**Version:** 0.3 (Post-implementation-planning — second self-reflective update)
**Date:** 2026-06-16
**Status:** Requirements (implementation-ready)
**Owner area:** `src/startd8/benchmark_matrix/` (Summer-2026 model benchmark)
**Companion:** `MULTIPHASE_JUDGING_RESEARCH_NL_ARTIFACTS.md` (the not-readily-judgeable artifacts)
**Plan:** `MULTIPHASE_JUDGING_READILY_JUDGEABLE_PLAN.md` (the planning pass that drove v0.3)

---

## 0. Planning Insights (Self-Reflective Update)

> This section records what changed between v0.1 (pre-grounding) and v0.2 after reading the
> scoring surfaces (`scoring.py`, `rescore.py`) and the persisted `.artifacts/` of completed
> Round-3 cells. Six corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Each cell has 3 drafts + 3 reviews | Iteration count **varies** — emailservice cell had 1 draft, cartservice had 3 | Trajectory is variable-length (N≥1); metrics must degrade when N=1 |
| "review-revised code" is a separate judgeable artifact | Reviews are **NL critique only**; the revision is the *next draft* | Reviews dropped from this doc → companion research doc; code set = `draft-1..draft-N` |
| `score_file` can ingest a draft as-is | `score_file(path, profile, …)` needs a real file path with the language's extension + a resolved `LanguageProfile`; drafts are **raw code saved as `.md`** (0 fences) | Add a trivial normalize step: write draft bytes → temp file with canonical extension → resolve language → score |
| One trajectory per cell | `.artifacts/` are **per-feature** (`<Feature>__<lang>__…-draft-N.md`); a multi-feature service has multiple draft chains but one cell-level on-disk score | Trajectory is **per-feature**, with a per-cell rollup; OB services are mostly single-feature (≈1:1) |
| Drafts need markdown extraction | Drafts are raw code to EOF, no code fences | Extraction is byte-copy + extension fix, not a markdown parser |
| Compile gate will turn drafts green | C#/Python drafts hit the **same missing gRPC/proto wall** as the final → `deps_missing`/degrade | Draft `compile_ok` degrades identically; structural still scores; this is expected, not a bug |

**Resolved open questions:**
- **OQ-1 (v0.1) → Advisory v1.** The trajectory is **diagnostic/additive**, not a new ranking term. It does NOT alter the leaderboard headline composite (same posture as Semantic Compliance v1).
- **OQ-2 (v0.1) → Reuse `rescore.py` exactly.** The per-feature draft loop parallels `rescore_run`'s cell loop (`resolve_generated_file` → `score_file`); a new sibling script reuses the same primitives at $0.

### 0.1 v0.2 → v0.3 (Post-Implementation-Planning)

> Writing the implementation plan (`…_PLAN.md`) against the real scoring code falsified the central
> assumption of v0.2 — that `score_file` would yield a per-draft **quality**. It does not. This is
> the reflective loop catching a wrong abstraction at document cost. Nine discoveries (D1–D8, D-COV,
> D-NEW); the high-value ones:

| v0.2 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| `score_file(draft)` gives a quality score | `score_file` **reuses a stored `structural_quality`** and only re-runs the **compile gate** (`rescore.py:165`). Drafts have **no** structural score; `compute_composite(structural=None)` floors to 0. | **The readily-judgeable signal is the per-draft COMPILE VERDICT, not a quality.** Reframed FR-2/4/5. |
| Quality trajectory `[q1…qN, final]` | Only `compile_ok`/`degraded` are valid per-draft for free; structural-per-draft needs `validate_disk_compliance` + the cell's contract and is ill-defined on an unassembled file | **Quality/structural trajectory → Tier B (deferred, OQ-E).** v1 is compile-based. |
| Convergence is the headline metric | **207/299 (69%) of drafted cells have only 1 draft** — convergence applies to just **92 cells** | **Split metrics:** `first_draft_compiles` is **universal (299 cells)**; convergence is a **subsample (92, report n)**. |
| Write trajectory into `cells.json` | `CellResult` is a fixed dataclass (touching it hits `__all__`/tests per CLAUDE.md) | **Sidecar `phase-trajectory.json`** — decoupled, and structurally enforces FR-10 (can't leak into ranking). |
| (not present) | `first_draft_compiles` + `iterations_to_first_compile` are **net-new, $0, universal** signals the board lacks — and more discriminating than structural (which saturates) | **D-NEW quick win promoted to first-class FR-5a/5b.** |

**Resolved/added open questions:** OQ-2 (v0.1) reused-as-planned; **OQ-E added** (Tier-B contract
availability); coverage confirmed worthwhile (74%, rising after the OpenAI merge).

*See §6 for the open questions that remain after planning.*

---

## 1. Problem Statement

The benchmark makes **~8 LLM calls per feature** (spec → draft×N → review×N → integration) but **judges exactly one artifact per cell**: the final, fully-integrated on-disk file (`score_file` on the resolved primary file → one `quality`/`structural_quality`/`compile_ok`). The intermediate **draft** artifacts are full, self-contained code in the same language — already persisted to `.artifacts/` — and are **discarded ungraded**. That is latent, *readily-judgeable* signal: the existing `score_file` (structural + compile gate) applies to them with no new mechanism and **no new LLM spend** (Mottainai: generate once, re-score free).

| Output (per feature) | Form | Currently judged? | Readily judgeable? |
|----------------------|------|-------------------|--------------------|
| `spec` | NL | no | **no** → companion doc |
| `draft-1 … draft-N` | full code | **no** | **yes** (this doc) |
| `review-1 … review-N` | NL critique (+ self-score) | no | **no** → companion doc |
| `integration` / final on-disk file | full code | **yes** | yes (already done) |

**Goal:** run the existing **compile gate** on every draft, producing a **per-feature compile trajectory** `[compiles(draft-1), …, compiles(draft-N), compiles(final)]`, and derive metrics — headline `first_draft_compiles` (universal) plus refinement signals on the multi-draft subsample — all as a **$0 re-score of persisted artifacts**. (Per-draft *quality/structural* is Tier B, deferred — §0.1 D1/D2: `score_file` reuses a stored structural score that drafts don't have.)

## 2. Requirements

**FR-1 — Discover draft artifacts.** For each cell, enumerate per-feature draft artifacts in
`<sandbox>/.startd8/benchmark-output/generated/.artifacts/*-draft-*.md`, grouped by feature key
and ordered by iteration index N. Tolerate variable N (≥1) and multiple features per cell.

**FR-2 — Compile-judge each draft (v1 scope).** Normalize each draft to a temp file carrying the
language's canonical extension — resolved from the **artifact name / seed**, NOT the `.md` path
(D6) — then run the **existing compile gate** via `score_file(path, profile, cfg=SandboxConfig(
no_network=True), structural=None)` and read **`compile_ok` + `degraded`** only. The composite
`value` is intentionally ignored: without a structural score it is not a meaningful quality (D1/D2).
A per-draft *quality/structural* score is **Tier B**, deferred (see FR-5c, OQ-E).

**FR-3 — Fair classification, reused.** Drafts pass through the **same** compile-failure
classification as final cells: a missing external dependency (gRPC/proto stubs) → `deps_missing`/
degrade (FR-J2/FR-C3), never a catastrophic zero. Reuse `is_missing_deps_failure` /
`classify_compile_failure` unchanged (it runs inside the compile gate, free).

**FR-4 — Emit a per-feature compile trajectory.** Produce
`trajectory = [{n, compiles, degraded} for draft-1…draft-N] + {final: compile_ok}`, keyed by
`(cell_id, feature)`. The final point reuses the **stored** `compile_ok` from `cells.json` — do not
recompute the final (D8).

**FR-5 — Derive metrics, tiered by availability** (per feature → per-cell rollup):

*FR-5a — Universal (every drafted cell, N≥1; ~299/405 today):*
- `first_draft_compiles` — did `draft-1` pass the compile gate (or degrade vs genuinely fail)? **Raw
  model skill before refinement** — net-new, the headline metric (D-NEW).
- `final_compiles` — the stored final `compile_ok` (the endpoint).

*FR-5b — Refinement subsample (cells with ≥2 drafts; ~92/405 today — report `n` explicitly):*
- `iterations_to_first_compile` — index of the first compiling draft (how many tries the model
  needed). Net-new (D-NEW).
- `compile_convergence` — did the chain go broke → compiling across iterations?
- `monotonicity` — fraction of steps that did not regress (compiling → broken counts against).

*FR-5c — Tier B (deferred, NOT v1):* per-draft `structural`/`quality` and `convergence_delta` —
requires `validate_disk_compliance` + the cell's forward-manifest contract; ill-defined on an
unassembled draft. Gated by OQ-E.

**FR-6 — $0, persisted-only.** Operate exclusively on already-persisted artifacts. No regeneration,
no LLM calls, no network. Same Mottainai guarantee as `rescore_ob_benchmark.py`.

**FR-7 — Per-cell rollup.** When a cell has multiple features, report per-feature trajectories AND a
cell-level rollup (default: mean of per-feature `first_draft_quality` / `convergence_delta`; report
per-feature detail so the rollup is never the only view).

**FR-8 — Persistence & surfacing (sidecar, not a cell field).** Write a **`phase-trajectory.json`
sidecar** keyed by `cell_id` (NOT a `CellResult` field — D5: avoids `__all__`/test churn AND
structurally enforces FR-10, since a sidecar cannot enter `aggregate_cells`). Add a **"Refinement
trajectory"** scorecard section that reads the sidecar when present (absent → omit). Ship
`scripts/rescore_phase_trajectory.py` mirroring `rescore_ob_benchmark.py`
(`run_dir`, `--write`, `.bak`, preview-by-default).

**FR-9 — Graceful degradation.** When a cell has no draft artifacts (older runs, or a cell that
didn't persist drafts), mark its trajectory `not computed` and continue — never fail the pass.

**FR-10 — Advisory, non-ranking (v1).** The trajectory MUST NOT change the leaderboard's headline
composite or model ranking. It is a diagnostic dimension (like Semantic Compliance v1). Feeding any
trajectory metric into the composite is explicitly out of scope for v1 (revisit per OQ-A).

## 3. Non-Requirements

- **Not** scoring `spec` or `review` artifacts — those are NL and have no reliable judge yet
  (companion research doc).
- **Not** computing a per-draft **structural/quality** score in v1 — that's Tier B (FR-5c/OQ-E);
  v1 is the **compile gate only** (D1/D2). v1 deliberately does not reproduce the final cell's
  composite for drafts.
- **Not** regenerating, re-running, or re-prompting anything (no spend).
- **Not** changing the composite formula, pass-threshold, or model ranking (FR-10).
- **Not** executing drafts as running servers (behavioral/Track-2 coverage of drafts needs a
  per-draft sandbox + server boot — deferred, OQ-C).
- **Not** a convergence *requirement* on models — we measure the trajectory, we don't gate on it.

## 4. Design Sketch (informed by the planning pass)

- **Reuse `rescore.py` primitives.** The cell loop in `rescore_run` (cells → `sandbox_dir_name` →
  `resolve_generated_file` → `score_file` → re-aggregate) is the template. The new pass adds a
  per-feature inner loop over `.artifacts/*-draft-*.md`.
- **Draft → scorable file:** read draft bytes, write to `tmp/<feature>.<ext>` where `<ext>` comes
  from `LanguageProfile` (resolved from the seed's `target_files` language), then `score_file`.
- **Language resolution:** the feature-artifact name encodes the language (`…__csharp__…`); fall
  back to `resolve_language` over the seed's `target_files`.
- **Output schema (sidecar `phase-trajectory.json`, keyed by `cell_id`):**
  ```json
  "<cell_id>": {
    "features": [{"feature": "...",
                  "drafts": [{"n":1,"compiles":true,"degraded":false}, {"n":2,...}],
                  "final_compiles": true,
                  "first_draft_compiles": true, "iterations_to_first_compile": 1,
                  "compile_convergence": false, "monotonicity": 1.0}],
    "rollup": {"first_draft_compiles": 1.0, "n_drafts_max": 2}, "status": "computed"
  }
  ```
  (`status: "not computed"` when the cell persisted no drafts.)

## 5. Validation

- **Determinism:** re-running the pass on an unchanged run is byte-identical (idempotent), like
  `rescore_ob`.
- **Sanity:** `q(final)` in the trajectory equals the cell's existing `quality` (the final point is
  the already-scored file) — a cross-check that the new path agrees with the live scorer.
- **Coverage log:** report `<computed>/<total>` cells and how many were `not computed` (no drafts),
  so thin coverage is never silently read as full (HAYAI/no-silent-caps).
- **Pilot:** run on the rescored `round3` ($0) and eyeball: does `first_draft_quality` rank models
  differently than `final_quality`? (the hypothesis: cheaper models gain more from the loop).

## 6. Open Questions (post-planning)

- **OQ-A — Should a refinement metric ever feed the composite?** v1 says no (advisory). A future
  "first-shot bonus" could reward models that compile on draft-1. Needs the companion doc's
  review-quality work first to avoid rewarding noise.
- **OQ-B — Multi-feature rollup function.** Mean is the v1 default; min (weakest-link) or
  per-feature-only may be more honest. Decide after seeing multi-feature OB cells (most are 1).
- **OQ-C — Behavioral trajectory.** Scoring each draft *functionally* (boot + loopback client, like
  Track 2) would show whether early drafts already work. Expensive (a sandbox per draft); deferred.
- **OQ-D — Single-draft reading.** 69% of drafted cells have one draft; confirm `draft-1`-only reads
  as "first-shot result," not "missing data" (FR-9 marks genuinely-absent drafts separately).
- **OQ-E — Tier-B feasibility (structural per draft).** Is the forward-manifest **contract**
  persisted per cell (needed by `validate_disk_compliance`)? And is disk-compliance even well-defined
  on a single unassembled draft? Resolve before any Tier-B (FR-5c) work.

---

*v0.3 — Second self-reflective update, post-implementation-planning. Central reframe: the
readily-judgeable signal is the **compile-gate trajectory**, not a quality trajectory (D1/D2).
FR-2/4/5 reframed; FR-5 split into universal (FR-5a) vs subsample (FR-5b) vs deferred Tier B (FR-5c);
FR-8 moved to a sidecar (hardens FR-10); 2 quick-win metrics promoted (D-NEW); FR-5c/OQ-E added for
structural. Coverage validated (74%). Ready for CRP review or implementation of Tier A.*
