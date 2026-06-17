# Multi-Phase Judging — Readily-Judgeable Outputs (Implementation Plan)

**Version:** 1.0
**Date:** 2026-06-16
**Plans:** `MULTIPHASE_JUDGING_READILY_JUDGEABLE_REQUIREMENTS.md` (v0.2 → drives v0.3)
**Status:** Planning pass (feeds the reflective update)

> This plan maps each requirement to concrete code in `src/startd8/benchmark_matrix/`. The act of
> planning falsified key assumptions in the v0.2 requirements; those discoveries are collected in §4
> and flow back into requirements v0.3.

---

## 1. Approach

Mirror `rescore.py`'s proven shape: load `cells.json`, loop cells with the **full** sandbox
coordinate, locate persisted artifacts, score with **existing** primitives, write an **additive**
output, never touch the ranking. The new pass adds a per-feature inner loop over draft artifacts.

**Tiered, because the planning pass found structural is not free per-draft (§4 D1–D2):**

| Tier | Signal | Cost | Mechanism | v1? |
|------|--------|------|-----------|-----|
| **A** | per-draft **compile verdict** (`compiles` / `degraded` / `deps_missing`) | **$0** | existing compile gate via `score_file(draft, profile, structural=None)`, read `compile_ok`/`degraded` | **YES** |
| **B** | per-draft **structural / disk-quality** (full composite trajectory) | non-trivial | `validate_disk_compliance` against each draft + the cell's forward-manifest contract | **NO — deferred** |

Tier A is the quick win *and* the higher-value signal: structural saturates among frontier models
(`scoring.py` docstring), so "does the draft compile / how many tries to first compile" is the
discriminating axis — and it's exactly the part available for free.

## 2. Per-Requirement Implementation Map

| FR | Implementation | Files / symbols (reuse) |
|----|----------------|-------------------------|
| **FR-1 Discover drafts** | Glob `<sandbox>/.startd8/benchmark-output/generated/.artifacts/*-draft-*.md`, group by feature key (prefix before `-draft-`), sort by N. Resolve `<sandbox>` with the **full coordinate** `sandbox_dir_name(service, model, rep, leverage, lead, drafter)` — the K2/K3 round-trip gotcha (`rescore.py:149`). NOTE: traverse hidden `.startd8` — Python `glob` `**` skips dotdirs; use `os.walk` or explicit path. | `runner.sandbox_dir_name`; `os.walk` |
| **FR-2 Score each draft** | Per draft: write bytes → `tmp/<feature>.<ext>` (`<ext>` from the resolved `LanguageProfile`), call `score_file(tmp, profile, cfg=SandboxConfig(no_network=True), structural=None)`, **read only `comp.compile_ok` + `comp.degraded`** (the composite `value` is meaningless without structural — §4 D1). | `scoring.score_file`, `CompositeScore`; `SandboxConfig` |
| **FR-2 language** | Resolve language from the **artifact name** (`…__csharp__…`) or the seed's `target_files`, **not** the `.md` extension (which would misresolve — §4 D6). | `languages.resolve_language`, seed `target_files` |
| **FR-3 Fair classification** | Free — it's inside the compile gate already: `classify_compile_failure` / `is_missing_deps_failure` run under `score_file`. A draft with absent gRPC stubs degrades, never floors. | `scoring.classify_compile_failure` |
| **FR-4 Trajectory** | Build `[{n, compiles, degraded} …]` per feature; endpoint = the **stored** final `compile_ok` from `cells.json` (no recompute — §4 D8). | cell `compile_ok` |
| **FR-5 Metrics** | Tier-A metrics only in v1: `first_draft_compiles` (N≥1 → **all 299 cells**), `iterations_to_first_compile`, `final_compiles`. Multi-draft-only (≥2 drafts → **92 cells**): `compile_convergence` (broke→compiles), `monotonicity`. Quality/structural deltas → Tier B. | pure functions |
| **FR-6 $0** | No regeneration; compile gate is local subprocess (`py_compile`/`gofmt`/`node --check`/`csc`/`javac`) — same tools the live scorer uses. | — |
| **FR-7 Rollup** | Per-feature + cell rollup (mean of `first_draft_compiles` as a rate; OB mostly 1 feature). | pure functions |
| **FR-8 Persistence** | **Sidecar `phase-trajectory.json`** keyed by `cell_id` — NOT a `CellResult` field (§4 D5). Decoupled, absent-safe, and structurally prevents leakage into `aggregate_cells` (enforces FR-10 by construction). Scorecard reads the sidecar if present. | new file; `scorecard.py` section |
| **FR-9 Degrade** | Cell with no `.artifacts` (106/405 — infra_fail + some failed) → `status:"not computed"`; never raises. | — |
| **FR-10 Advisory** | Guaranteed by FR-8 sidecar: trajectory never enters `CellResult`/`aggregate_cells`, so it cannot move the ranking. | — |

## 3. New surfaces to build (small)

- `src/startd8/benchmark_matrix/phase_trajectory.py` — `build_phase_trajectory(run_dir, seeds_dir) -> dict`
  (the loop + Tier-A scoring + metrics), mirroring `rescore.rescore_run`.
- `scripts/rescore_phase_trajectory.py` — CLI mirroring `rescore_ob_benchmark.py`
  (`run_dir`, `--write`, `.bak`, preview-default). Writes `phase-trajectory.json`.
- `scorecard.py` — one new "Refinement trajectory" section, reading the sidecar (absent → omit).

No edits to `CellResult`, `aggregate_cells`, `compute_composite`, or the leaderboard.

## 4. Discoveries (what planning revealed) → feeds requirements v0.3

| v0.2 Requirement | Planning discovery | Action on requirements |
|------------------|--------------------|------------------------|
| **D1** FR-2: "score each draft via `score_file` → quality" | `score_file` does **not** compute structural; it reuses the **stored** `structural_quality` (`rescore.py:165`) and only re-runs the compile gate. Drafts have **no** stored structural. | Reframe FR-2: v1 yields a **compile verdict** per draft, not a full quality. |
| **D2** FR-5: trajectory = quality `[q1…qN, final]` | `compute_composite(structural=None)` floors to 0 → a "quality" trajectory would be fake. But `compile_ok`/`degraded` are valid with no structural. | Trajectory is **compile-based** in v1; quality trajectory → Tier B / deferred. |
| **D3** FR-5 emphasis on convergence | **207/299 (69%) of drafted cells have only 1 draft.** Convergence/monotonicity apply to just **92 cells**. | Split metrics: `first_draft_compiles` (universal, 299) vs convergence (subsample, 92, report n). |
| **D4** structural per draft assumed cheap | Needs `validate_disk_compliance` + the cell's forward-manifest **contract** (persistence unverified) and is ill-defined on a single in-progress file (imports/reachability across an unassembled app). | Move to Tier B; add OQ for contract availability. |
| **D5** FR-8 "write a `phase_trajectory` block into `cells.json`" | `CellResult` is a fixed dataclass; new field touches `from_dict`/`to_dict`/`__all__`/tests (CLAUDE.md rule). | Reframe FR-8: **sidecar file**, not a cell field — also hardens FR-10. |
| **D6** FR-2 language from file | `resolve_language` keys off extension; a `.md` draft misresolves. | Resolve from artifact name / seed. |
| **D7** FR-1 sandbox lookup | Must use the **full** `sandbox_dir_name` coordinate (leverage/lead/drafter) or miss off-diagonal cells. | Bake the full coordinate into FR-1. |
| **D8** FR-4 endpoint recompute | Final `compile_ok` is already in `cells.json`. | Reuse stored value; don't recompute the final. |
| **D-COV** ROI unknown | **299/405 (74%)** cells have drafts; coverage rises after the OpenAI merge. | Worth building; add coverage-honesty reporting (FR-9). |
| **D-NEW** quick win | `first_draft_compiles` + `iterations_to_first_compile` are **net-new, $0, universal** diagnostics the board lacks — and more discriminating than structural. | Promote to first-class FRs in v0.3. |

## 5. Risks

- **Compile gate cost at scale:** 449 drafts × a subprocess compile each (C#/Java are the slow ones).
  Still $0 in LLM terms and far cheaper than generation; bound by running serially like `rescore_ob`.
- **Tier-B contract availability:** whether the forward-manifest contract is persisted per cell is
  unverified — that's the gate for any future structural-per-draft work (OQ).
- **Single-draft majority:** manage expectations — the headline value is first-draft-compile skill,
  not a rich convergence curve.

## 6. Step sequence

1. `phase_trajectory.py` Tier-A loop + metrics (FR-1..7, 9).
2. Sidecar persistence + `rescore_phase_trajectory.py` CLI (FR-8).
3. Scorecard section (FR-8 surfacing).
4. Pilot on rescored `round3` ($0): compare `first_draft_compiles` ranking vs `final` ranking.
5. (Deferred) Tier B structural-per-draft — only after contract-availability OQ resolves.

---

*Plan v1.0 — maps all 10 FRs; surfaced 9 discoveries (D1–D8, D-COV, D-NEW) that revise requirements
to v0.3. Headline: the readily-judgeable signal is the **compile-gate trajectory**, not a quality
trajectory — cheaper, universal, and more discriminating than the structural term v0.2 assumed.*
