# Multi-Phase Judging — Not-Readily-Judgeable Artifacts (Research Draft)

**Version:** 0.1 (Research agenda — NOT implementation-ready)
**Date:** 2026-06-16
**Status:** Research draft — open questions, candidate mechanisms, validation gates
**Companion:** `MULTIPHASE_JUDGING_READILY_JUDGEABLE_REQUIREMENTS.md` (the drafts, scorable today)

> **Read this as a research agenda, not a spec.** These artifacts have **no reliable scoring
> mechanism yet**. The point of this doc is to enumerate what we'd have to establish — and what
> could go wrong — *before* any score derived from them is allowed to influence the benchmark.
> Premature scoring here is worse than no scoring: a plausible-but-wrong spec/review grade would
> launder model self-assessment into an apparently-objective number.

---

## 1. The artifacts in scope

Per feature, the pipeline persists two natural-language artifacts we currently ignore:

| Artifact | Form (observed in Round-3 `.artifacts/`) | Why it resists deterministic judging |
|----------|------------------------------------------|--------------------------------------|
| `spec` | Implementation specification prose (task summary, requirements, acceptance criteria) | "Spec quality" has no compiler/test; quality = completeness + faithfulness to the seed, both subjective |
| `review-1 … review-N` | NL critique that **already contains a model self-score** (e.g. `Score: 81/100`, `Passed: True`) and per-requirement ✅/❌ | It is the model grading *its own* output; using it as truth is circular (self-preference bias) |

The drafts and the final code are scorable *today* (companion doc). These two are not — they need
research to become **reliable** signal.

## 2. Why "not readily judgeable" (the core risk)

1. **No ground truth.** A compile gate is objective; "is this spec good?" is not. Any score needs a
   rubric or a reference, both of which we'd have to author and validate.
2. **Self-preference / circularity.** The review artifact is the model judging itself. Its `81/100`
   correlating with *anything* must be measured, not assumed — a model that scores itself 90 on
   broken code is the failure mode, and that's exactly what we'd be trying to detect.
3. **Contamination surface.** An LLM-judge over OB specs may reward memorized upstream phrasing
   rather than task fidelity (cf. FR-47 contamination control). The judge inherits the contamination
   problem the leaderboard works to isolate.
4. **Cost & reproducibility.** LLM-judging is not $0 and not deterministic; it needs seed-pinning,
   temperature control, and inter-run stability before it can sit on a publication board.

## 3. Research Questions

- **RQ-1 — Does model self-review predict actual quality?** Correlate the persisted review
  `Score`/`Passed` against the final cell `quality` (and Track-2 behavioral coverage). **Cheap:** the
  review scores are already on disk; this is a $0 correlation study and the natural first experiment.
- **RQ-2 — Can spec quality be scored reliably?** Candidate signals: rubric-based LLM-judge;
  reference/gold-spec similarity (we authored the seeds — they are a partial gold); requirement-
  coverage (does the spec enumerate the seed's acceptance criteria?). Which, if any, correlates with
  downstream code quality?
- **RQ-3 — Does the review→draft loop actually help, and can the review get credit?** The companion
  doc measures `refinement_effectiveness` (quality gain across drafts) structurally. RQ-3 asks the
  harder question: did a *specific* review's suggestions cause the next draft's gain? (outcome
  attribution, not just correlation.)
- **RQ-4 — Defect-ledger recall of the review.** We already persist a defect ledger / semantic-
  compliance findings (ground-truth-ish defects). Measure the review's **precision/recall** against
  them: did the model's self-review catch the defects later tools found? This turns review quality
  into a measurable detection task with an existing reference.

## 4. Candidate Mechanisms (each needs validation before trust)

| Mechanism | Sketch | Reuses | Main risk |
|-----------|--------|--------|-----------|
| **LLM-judge + rubric** | A fixed rubric scores spec/review via `agenerate_structured` + a SKILL.md-as-system-prompt | Semantic Compliance (`SemanticVerificationResult`, K-7 socket), Tier Haiku→Sonnet | self-preference, contamination, cost, non-determinism |
| **Reference / gold compare** | Score spec against the seed's acceptance criteria (coverage %) | seeds in `docs/design/model-benchmark/seeds/` | seeds are partial gold; phrasing ≠ fidelity |
| **Outcome-correlation** | Treat review value = measured draft→draft quality gain (companion doc) | `phase_trajectory` (companion FR-4/5) | correlation ≠ causation (RQ-3) |
| **Defect-ledger recall** | Review precision/recall vs persisted defects | defect-ledger, semantic_compliance | ledger itself is imperfect ground truth |

## 5. Validation Gates (a score is NOT adopted until it passes)

Before any spec/review score is allowed onto a board or into the composite:
1. **Inter-rater reliability** — the LLM-judge agrees with itself across reruns (seed-pinned) and
   with a small human-labeled sample.
2. **Predictive validity** — the score correlates with an *independent* objective signal (final
   `quality`, Track-2 behavioral) at a pre-registered threshold; a self-review that doesn't predict
   real quality is rejected (that's the RQ-1 gate).
3. **Self-preference audit** — measure whether a model systematically over-scores its own output vs a
   neutral judge; if so, the self-score is unusable as truth.
4. **Contamination audit** — the judge does not reward memorized upstream phrasing (reuse FR-47
   CodeBLEU control as a covariate).
5. **Cost/reproducibility budget** — per-cell judge cost and run-to-run variance are within a stated
   ceiling.

Only signals that clear all five graduate from "research" to a companion *requirements* doc.

## 6. Suggested Sequence (cheapest, highest-information first)

1. **RQ-1 ($0):** correlate persisted review self-scores vs final quality / behavioral. If
   self-review is uncorrelated, that itself is a publishable finding and kills naive reuse.
2. **RQ-4 (low cost):** review vs defect-ledger precision/recall — reuses existing ground truth.
3. **RQ-2 (medium):** spec coverage vs seed acceptance criteria (deterministic first, LLM-judge
   second).
4. **RQ-3 (highest):** causal attribution of review→draft gains — only after the companion doc's
   trajectory data exists.

## 7. Explicit Non-Commitments

- This doc commits to **no implementation**. No scoring of spec/review ships from it directly.
- No spec/review score touches the leaderboard composite until it clears §5.
- The `81/100` self-scores are treated as **data to study**, never as truth, until RQ-1 says
  otherwise.

---

*v0.1 research draft. Companion to the readily-judgeable requirements. Next step: run RQ-1 as a $0
correlation study over the persisted Round-3 review artifacts — it gates everything else here.*
