# RQ-1 Findings — Does Model Self-Review Predict Actual Quality?

**Date:** 2026-06-16
**Status:** Result (the $0 gating study from `MULTIPHASE_JUDGING_RESEARCH_NL_ARTIFACTS.md` RQ-1)
**Data:** `results/round3/` (N=5 OB, repair-shadow), persisted `review-*.md` self-scores

---

## Question

The pipeline's `review-*.md` artifacts contain a **model self-assessment** (`Score: NN/100`,
`Passed: True/False`). RQ-1 asks: does that self-score predict the cell's *actual* quality? If not,
reusing it as a scoring term would launder optimistic self-grading into an apparent objective number
(the self-preference/circularity risk in the research doc). This is the **$0 gate** for the entire
Doc-2 review-scoring path.

## Method

For each cell, parse the **last** review iteration's `Score: NN/100` (the model's final
self-assessment), join to the cell's `quality`/`compile_ok` in `cells.json`, and correlate. $0,
read-only, persisted artifacts only. Manual Pearson + Spearman (no scipy dependency).

## Result

| Relationship | n | Pearson r | Spearman ρ |
|--------------|---|-----------|------------|
| self-score → final **quality** | 98 | 0.234 | **0.258** |
| self-score → **compile_ok** | 74 | 0.162 | — |

- **Self-review is a weak predictor of quality (ρ ≈ 0.26)** and weaker still of whether the code
  compiles (r ≈ 0.16).
- **Models are systematically optimistic:** mean self-score **0.90**, **88%** rate themselves ≥0.80,
  minimum only 0.38.
- **The `Passed` flag barely discriminates:** the model said `Passed` on 86/98 cells (88%) on a
  population where ~97% actually scored ≥0.5 — i.e. it says "pass" almost always, on a set that
  almost always passes. Near-zero discriminating power.

## Verdict

**Self-review does NOT support use as a quality term.** It is weakly correlated, poorly calibrated,
and self-congratulatory — exactly the failure mode the research doc's §5 validation gates exist to
catch. Naive reuse of the `81/100`-style self-scores is **rejected** by this gate.

## Honest caveats (why this is a floor, not a verdict on the *idea*)

1. **Range restriction.** Final `quality` saturates (mean 0.949, var 0.0158) — low variance
   attenuates any correlation. The weak ρ is *partly* "there's little quality variance to predict."
2. **Coverage.** Only 119/299 reviewed cells used the parseable `Score: NN/100` format; the format
   is not universal.
3. **Single run** (round3, repair-shadow); re-run on `round3-final` after the OpenAI merge.

## What this redirects the research toward

- **RQ-4 (review vs defect-ledger recall) is now the priority** — and feasible: the **per-cell
  `defect-ledger/` IS persisted** (confirmed while resolving OQ-E). A defect ledger is a
  higher-variance, more objective ground truth than the saturated quality score, so "did the review
  *catch the defects later tools found*" is a sharper test than "did its number match the quality."
- **Better target for any future self-score test:** correlate against a higher-variance signal —
  Track-2 behavioral coverage, or the new **`first_draft_compiles`** (Tier A) — not the saturated
  composite.

*RQ-1 complete. Outcome: self-review rejected as a standalone quality signal (ρ≈0.26, mean self-score
0.90); research redirected to RQ-4 (defect-ledger recall, ground truth already on disk).*
