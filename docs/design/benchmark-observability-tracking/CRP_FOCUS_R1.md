# CRP Focus — Summer 2026 Model Benchmark (Round 1)

Where reviewer input is most valuable. Weight suggestions toward these concerns.

## Focus 1 — Fairness / methodology integrity
Is `compute_disk_quality_score` (contract 0.4 / imports 0.2 / stubs 0.2 / semantic 0.2) a
*defensible* "quality" claim when published, especially across 5 languages with different toolchains?
Does disk-compliance correlate with "the code actually works"? What's the minimum credible quality
signal (compile + tests) before this can be called a benchmark rather than a heuristic?

## Focus 2 — Cost-control / budget guardrails
The matrix is tiers × services (9) × models (~10) × N repetitions. There is no hard budget stop in the
plan. What guardrails (pre-run cost estimate, per-cell cap, abort-on-budget, dry-run sizing) prevent a
runaway spend? OQ-8 is unresolved — what's the safe default?

## Focus 3 — Reproducibility integrity
FR-28 provenance + FR-19 kit. Are pinned model-version strings actually stable (vendors silently update
"flagship" aliases)? Is sandbox isolation enough? What confounders (network, rate-limit retries, time-of-day
model load) undermine reproducibility, and how should they be recorded?

## Focus 4 — Publication / credibility risk
This is a self-authored benchmark where the user's own SDK is the harness and Fable 5 (Anthropic) is the
hero of the framing. What are the conflict-of-interest, cherry-picking, and methodology-transparency risks?
What would a hostile reader on HN/Reddit attack first, and what disclosures/controls neutralize that?

## Focus 5 — Statistical validity of N-repetition variance
With small N per cell, are mean/stdev meaningful? What N is defensible? Should we report confidence
intervals, non-parametric stats, or per-cell pass/fail distributions instead? How are LLM nondeterminism
(temperature, sampling) and rare catastrophic failures (one $0-quality run) handled in the aggregate?
