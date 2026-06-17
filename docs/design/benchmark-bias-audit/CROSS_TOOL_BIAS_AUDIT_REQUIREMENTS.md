# Cross-Tool Differential Bias Audit — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-17
**Status:** Draft (planning-corrected; pre-implementation)
**Plan:** `CROSS_TOOL_BIAS_AUDIT_PLAN.md`
**Scope:** Detect and quantify Anthropic-authorship bias in the Summer-2026 benchmark **inputs**, by
independently re-authoring them with OpenAI **Codex** and Google **Antigravity** and running two
differential tests. Pilot on the Liferay-derived **pricing seed**.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 and v0.2 after planning the experiment. The planning pass produced 6
> corrections; two reshape the experimental design.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| Re-author all 3 artifacts at once, then diff | **Conflates spec-bias and suite-bias** (the suite's values depend on the spec's choices). | **FR-2 refactored to a *factored* design** (Exp-A: fix spec, vary suite; Exp-B: fix behavior, vary spec). New FR-2a/2b. |
| Equivalence = suites agree on the correct oracle | A correct oracle barely discriminates — almost any plausible suite passes. | **FR-4 now uses a mutant battery** (new FR-4 + FR-12). Resolves OQ-3. |
| Score-impact = does swapping spec change scores | Confounded by spec *quality* (uniform shifts ≠ bias). | **FR-6 now tests the model×spec *interaction*** (each vendor's model relatively favored by its own vendor's spec). |
| One sample per tool | Agents are non-deterministic; 1 sample conflates bias with run-variance. | **New FR-11: N samples per tool**, statistical divergence. Resolves OQ-5. |
| "Neutral brief" is straightforward | The brief is the crux; deriving it from Claude's doc pre-injects bias. | **FR-1 sharpened**: derive from Liferay source + bare contract schema; tag each item FIXED vs OPEN. |
| Triangulation: agree=neutral, diverge=bias | 2-vs-1 splits are ambiguous (could be Claude-bias or a shared non-Claude convention). | **FR-7 now requires unanimity** for a neutrality verdict; majority is a flag, not proof. |

**Resolved open questions:**
- **OQ-3 → mutant battery** (FR-12): equivalence is measured against the oracle *plus* K deliberately-buggy servers.
- **OQ-5 → sample, don't force determinism** (FR-11): N samples per tool; treat divergence statistically.
- **OQ-1 / OQ-2 / OQ-4** remain open as implementation/calibration items (auth wiring, brief neutrality review, score-impact spend) — see §4.

---

## 1. Problem Statement

The benchmark compares models across vendors, but its **inputs and infrastructure** were authored
largely by Claude via Claude Code: the seed `.proto` contracts, the `requirements_text` spec, and the
SDK-authored ground-truth suites. This is a systematic-bias surface — Claude-authored phrasing,
contract shapes, or ground-truth interpretations could subtly favor Anthropic models — and it is the
single most attackable validity claim for a published cross-vendor benchmark ("the author used one
vendor's tool to build the test").

**Mitigation:** independently re-author the same inputs with Codex (OpenAI) and Antigravity (Google)
from a neutral source, then measure (a) whether the independently-authored artifacts *agree*
(input-equivalence) and (b) whether swapping them changes model *rankings* (score-impact). Where all
three independent authors agree, the input is likely neutral; where they diverge, that is where
author-bias or genuine source-ambiguity lives.

| Input artifact (pricing seed) | Authored by | Bias risk |
|---|---|---|
| `pricing.proto` (contract) | Claude | shape/field choices favor Claude idioms |
| `requirements_text` (spec) | Claude | phrasing/structure easier for Claude to satisfy |
| `pricing_suite.py` (ground truth) | Claude | the *interpretation* of correct behavior is Claude's |

## 2. Requirements

**FR-1 — Neutral task brief (FIXED/OPEN tagged).** Author a vendor-agnostic brief describing the
reproduction task from the *upstream source* (the Liferay pricing capability + the bare benchmark
seed-contract schema), NOT from Claude's existing artifacts. Each requirement is tagged **FIXED**
(a true contract constraint — single RPC, decimal-string money, gRPC, the seed JSON shape) or
**OPEN** (a semantic choice under test — rounding default, chain-vs-addition, fixed-amount basis,
tax/discount ordering, error taxonomy, field naming). The brief must not leak Claude's resolution of
any OPEN item. Human-reviewed for Claude-idiom leakage (the honesty control).

**FR-2 — Factored re-authoring (not all-at-once).** Re-authoring decomposes into two isolated
experiments so spec-bias and suite-bias don't conflate:
- **FR-2a — Suite-author experiment:** hold the spec FIXED (Claude's), have each tool author only the
  **ground-truth suite**.
- **FR-2b — Spec-author experiment:** hold the *behavior/oracle* fixed, have each tool author only the
  **spec** (and, if it chooses, the proto) from the brief.
Each runs with a Claude control for symmetry.

**FR-3 — Automatable, reproducible runs.** Drive Codex and Antigravity via CLI/API. Capture prompt,
tool+model version, parameters, raw output, and timestamp for each run so the audit is re-runnable.
Verify each tool's headless path at the start; if Antigravity has no headless mode, fall back to
documented manual capture and flag the asymmetry.

**FR-4 — Input-equivalence via mutant battery.** Cross-validate the FR-2a suites against the
known-correct Node oracle **plus a battery of mutant servers** (FR-12). Two suites are equivalent iff
they produce the same pass/fail vector across the whole battery. A suite that misses a mutant the
others catch reveals an author blind spot — localize it to the missing assertion.

**FR-5 — Spec/contract divergence catalog.** Diff the FR-2b specs and protos for semantic divergences
(rounding default, strategy default, fixed-amount basis, tax ordering, error taxonomy, field naming).
Classify each as legitimate source-ambiguity vs author-specific choice.

**FR-6 — Score-impact via model×spec interaction.** Run the same 3-flagship roster against each spec
variant (Claude/Codex/Antigravity), holding everything else constant. The bias signal is **not** a
marginal score shift (that is spec *quality*, which moves all models together) but the **interaction**:
a vendor's model scoring *relatively* higher under its own vendor's spec. Report the interaction, not
just per-spec means.

**FR-7 — Attribution via unanimity rule.** **Unanimous** agreement across all three independent authors
→ input deemed neutral (the only strong signal). Any divergence — including a 2-vs-1 split, which is
ambiguous (Claude-bias vs a shared non-Claude convention) — is a **flag for human adjudication**, not an
automatic bias verdict. Distinguish vendor-author bias from tool-capability differences.

**FR-8 — Bias-audit report.** Per seed: equivalence matrix, divergence catalog, score-impact deltas,
and a verdict (neutral / biased-and-corrected / ambiguous-flagged).

**FR-9 — Remediation loop.** When bias is found, the fix (neutralize phrasing, pin an ambiguous
semantic in the spec) feeds back into the seed; re-audit.

**FR-10 — Honest provenance.** Record that Codex (OpenAI) and Antigravity (Google) carry their own
vendor bias; the method is triangulation, not bias-free authorship. Publish methodology + raw artifacts
for external scrutiny.

**FR-11 — Sampling for non-determinism.** Take **N samples per tool per artifact** (N ≥ 3 to start).
Treat cross-tool divergence statistically: a difference counts as author-bias only if it is consistent
across a tool's samples and separable from within-tool variance — not a one-off draw.

**FR-12 — Mutant reference battery.** Maintain a battery = the known-correct Node oracle + K mutant
servers, each injecting one semantic error (wrong rounding mode, addition-when-chain, tax-before-discount,
ignored cap, float arithmetic, promo-min inverted, …). Each mutant targets one OPEN choice from FR-1, so a
suite's pass/fail vector reveals which behaviors it actually pins. The battery is the discrimination
instrument for FR-4.

## 3. Non-Requirements

- **Not** reproducing the SDK code, scoring, or harness — inputs only (per scope decision).
- **Not** a bias-free oracle — triangulation across three biased authors, not purity.
- **Not** auto-correcting — divergences go to human adjudication.
- **Not** the OB seeds in the pilot — pricing seed first.

## 4. Open Questions

- **OQ-1** Exact Codex / Antigravity CLI/API invocation + auth (Doppler-managed keys; verify Antigravity headless path — FR-3).
- **OQ-2** Calibrating FR-1 brief neutrality: FIXED/OPEN tagging + human review is the mechanism, but how loose is too loose? (Resolved in approach; needs a review pass on the actual brief.)
- **OQ-4** Score-impact spend (~3 spec variants × pricing-only × 3 flagships × N=5 ≈ $8) and the interaction-model statistics (FR-6) — calibrate N for power.
- **OQ-3 → resolved** (FR-12 mutant battery). **OQ-5 → resolved** (FR-11 sampling).

---

*v0.2 — Post-planning self-reflective update. Experiment refactored to a factored design (FR-2a/2b),
2 requirements added (FR-11 sampling, FR-12 mutant battery), 3 sharpened (FR-1 FIXED/OPEN, FR-6
interaction, FR-7 unanimity), 2 open questions resolved. The loop earned its keep: the spec-vs-suite
conflation and the quality-vs-bias confound would otherwise have invalidated the audit's conclusions.*
