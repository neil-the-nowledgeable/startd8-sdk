# Tier A Pilot — Cross-Round `first_draft_compiles` (Findings)

**Date:** 2026-06-16
**Status:** Pilot result (the FR-5 validation question, run on round2-rescored + round3)
**Data:** persisted `phase-trajectory.json` sidecars (round2-expose-shadow + round2-openai, round3)

---

## The question (from the requirements §5)

> "Does `first_draft_compiles` rank models differently than final quality? (hypothesis: cheaper
> models gain more from the refinement loop.)"

## Result — the metric saturates

| Round | provider | cells | first-draft-compiles | none | multi-draft | converged |
|-------|----------|------:|---------------------:|-----:|------------:|----------:|
| 2 | anthropic | 27 | 100% | 0 | 6 | 0 |
| 2 | gemini | 27 | 100% | 0 | 6 | 0 |
| 2 | openai | 27 | 100% | 0 | 16 | 0 |
| 3 | anthropic | 112 | 100% | 0 | 22 | 0 |
| 3 | gemini | 135 | 99% | 2 | 38 | 2 |
| 3 | openai | 52 | 98% | 1 | 32 | 1 |

**`first_draft_compiles` saturates at 98–100% across every provider and both rounds.** At the
syntax/compile level, frontier models almost never emit a non-compiling first draft (degrade =
absent-deps counts as excused, per FR-3). It does **not** discriminate among models.

## Interpretation

This **confirms the benchmark's core thesis from the other direction:** just as *structural*
compliance saturates among frontier models (`scoring.py` docstring), so does *compile-ability*. The
discriminating axis is **functional/behavioral** ("does the service actually run and answer
correctly"), not "does it compile." So:

- **Tier A's headline metric is a diagnostic, not a ranking axis.** The advisory/non-ranking posture
  (FR-10) was exactly right — feeding `first_draft_compiles` into the composite would add ~no signal.
- **The signal that *is* there lives in the tail and the loop:** the rare non-compiling first drafts
  (3 in round3: gemini ×2, openai ×1) and the `converged` cases (3 in round3 — draft-1 broke, a
  later draft compiled). These are worth surfacing as exceptions, not as a leaderboard column.
- **Real per-draft discrimination needs Tier B (structural per draft) or behavioral-per-draft** —
  both deferred/harder, and now better motivated: the cheap compile signal has been shown to saturate.

## What this changes

- Keep Tier A **shipped but advisory** — surface the **non-compiling tail + convergence cases** in the
  scorecard (exceptions), not a per-model compile-rate column (which would read ~100% for everyone).
- Re-weight the roadmap: the value of a *behavioral* trajectory (OQ-C) rises now that compile is shown
  saturated; structural-per-draft (Tier B / OQ-E) is the more discriminating-but-costly path.

*Pilot complete. Outcome: `first_draft_compiles` saturates (98–100%) → advisory diagnostic, not a
ranking term (FR-10 vindicated). Discrimination is in the non-compiling tail + the convergence
subsample; broad per-draft discrimination needs behavioral/structural, not compile.*
