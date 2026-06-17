# Cross-Tool Differential Bias Audit — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-17
**Tracks:** `CROSS_TOOL_BIAS_AUDIT_REQUIREMENTS.md` (drove this plan; updated to v0.2 by it)

Maps the audit to concrete steps over the pricing-seed artifacts (`pricing.proto`,
`requirements_text` in `seed-pricingservice.json`, `pricing_suite.py`) and the flagship runner
(`scripts/run_flagship_benchmark.py`), and records what planning revealed.

---

## Discoveries (feed the reflection pass)

| What v0.1 assumed | What planning revealed |
|---|---|
| Re-author all 3 artifacts at once, then diff (FR-2/FR-4/FR-5) | **CONFLATED.** The suite's expected values depend on the spec's semantic choices. If a tool authors a different spec AND suite, suite-disagreement can't be told apart from a consequence of its different spec. The experiment must be **factored**: (i) fix the spec → vary only the suite (isolates *suite*-author bias); (ii) fix the behavior/oracle → vary only the spec (isolates *spec*-author bias). |
| Equivalence = suites agree on the correct oracle (FR-4) | A correct oracle is passed by almost any plausible suite → it barely discriminates. Need a **battery of mutant (deliberately-buggy) reference servers**; a biased/weak suite fails to catch mutants a good suite catches. Equivalence = suites produce the same pass/fail vector across the whole battery. (Resolves OQ-3.) |
| Score-impact: does swapping spec change scores (FR-6) | **Confounded by spec quality.** A clearer/vaguer spec shifts *all* models uniformly — that's quality, not bias. The bias signal is an **interaction**: each vendor's model scoring *relatively* higher under its own vendor's spec. Analyze model×spec interaction, not marginal score change. |
| One sample per tool per artifact | These agents are **non-deterministic**; one sample conflates author-bias with run-variance. Need **N samples per tool per artifact**; treat divergence statistically (does Claude consistently differ, or is it within-tool noise?). (Resolves OQ-5 — can't force determinism; sample instead.) |
| "Neutral brief" is straightforward (FR-1) | The brief is the crux and the hardest artifact. Derived from Claude's requirements doc → bias pre-injected. Must derive from the **Liferay source + the bare seed-contract schema**, and explicitly enumerate which constraints are *fixed* (single RPC, decimal money, gRPC) vs which semantic choices are *left open* (rounding default, chain/addition, fixed-amount basis, tax ordering) — the open ones are exactly what's under test. |
| Triangulation: agree=neutral, diverge=biased (FR-7) | 2-vs-1 splits are ambiguous: Claude-vs-(Codex+Antigravity) could be Claude bias OR the other two sharing a non-Claude convention. Only **unanimous agreement** is a strong neutrality signal; majority is a flag, not proof. Needs explicit decision rules. |
| Tool access is uniformly automatable | Verify per-tool at plan time: Codex needs `OPENAI_API_KEY`, Antigravity needs Google auth (both via Doppler); Antigravity has historically been IDE-interactive — confirm a headless/CLI path exists or fall back to scripted-capture. Capture tool+model version per run (FR-3). |

## Step-by-step

**S1 — Neutral brief** (`brief/pricing-task-brief.md`). Author the FR-1 brief from Liferay source +
the seed-contract schema; tag each requirement `FIXED` or `OPEN`. Reviewed by a human for Claude-idiom leakage.

**S2 — Reproduction harness** (`scripts/run_bias_reproduction.py`). Drive Codex + Antigravity (+ Claude
control) via CLI/API, N samples each, capturing prompt/version/output/timestamp to a durable batch dir.
Dry-run-by-default; keys via `doppler run`.

**S3 — Mutant reference battery** (`bias_audit/mutants/`). The known-correct Node oracle + K deliberately-buggy
mutants (wrong rounding mode, addition-when-chain, tax-before-discount, off-by-cap, float arithmetic, ...).
Each mutant targets one semantic choice.

**S4 — Factored experiment A (suite-author bias).** Fix the Claude spec; have each tool author only the
**suite** (N samples). Run every suite against the mutant battery → pass/fail vectors → equivalence matrix.
A suite that misses a mutant the others catch reveals an author blind spot.

**S5 — Factored experiment B (spec-author bias).** Each tool authors only the **spec** (N samples) from the
brief. Build a seed variant per spec; run the 3 flagships against each via the flagship runner; analyze the
**model×spec interaction** for the bias signal. (~3 variants × pricing-only N=5 ≈ $8.)

**S6 — Divergence catalog + attribution** (`bias_audit/divergences.md`). Catalog proto/spec semantic
divergences; classify source-ambiguity vs author-choice; apply the unanimity/triangulation rules.

**S7 — Report + remediation** (`bias_audit/REPORT-pricing.md`). Equivalence matrix, interaction deltas,
divergence verdicts; for each confirmed bias, the corrective seed edit + re-audit.

## Risks
- Antigravity headless automation may not exist → fall back to documented manual capture (still reproducible
  via captured transcripts), but flag the asymmetry vs Codex.
- N must be large enough to separate author-bias from agent variance; small N → inconclusive. Budget samples.
- The brief can never be perfectly neutral; its FIXED/OPEN tagging + human review is the honesty control.
