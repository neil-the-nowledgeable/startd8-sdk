# S4 v2 Evidence 1200s Bias Analysis

Date: 2026-07-05
Batch: `pricing-cross-tool-authoring-v2-evidence-1200s`
Branch: `codex/s4-v2-bridge-aliases`
Base: `faef9d1f Merge pull request #92 from neil-the-nowledgeable/codex/authoring-prompt-current-workdir`

Source artifacts:

- `.startd8/bias-audit-store/pricing-cross-tool-authoring-v2-evidence-1200s/reconciliation-report.json`
- `.startd8/bias-audit-store/pricing-cross-tool-authoring-v2-evidence-1200s/intake-ledger.json`
- `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-after-dispositions/s4-preflight.json`
- `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-after-dispositions/mutant_kill_matrix.csv`
- `analysis/S4_V2_REFERENCE_ORACLE_FAILURE_DISPOSITION.md`
- `analysis/s4-pre-registration-v2-evidence-1200s.json`
- `analysis/s4-suite-dispositions-v2-evidence-1200s.json`

## Executive summary

The real 30-run authoring batch completed and was promoted cleanly:

- authoring execution: 30/30 completed
- reconciliation: 30/30 accepted
- intake normalization: 30/30 accepted
- suite-author artifacts admitted to S4: 15
- reviewed bridge execution: completed across 165 cells

Reviewer disposition of the original 9 reference-oracle failures changed the S4
picture materially:

- 6 failures were bridge-harness artifacts and cleared after the supplemental
  `run_all` check was corrected to use the callable adapter seam.
- 2 failures were generated-suite over-specifications and are now reviewed
  exclusions from S4 evidence.
- 1 failure remains unresolved: run 03 exposes a declared flattened
  decimal-string/enum-alias seam that the current bridge does not yet support.

S4 therefore remains fail-closed, but the evidence no longer supports the earlier
OpenAI-specific 0/5 reference-admission signal. After correction and disposition,
each vendor has 4 reference-passing suites out of 5 authored suite rows.

## S4 execution status after disposition

Post-disposition S4 verification:

- `s4-preflight.json` status: `blocked`
- remaining errors: 1
- only remaining failing row: `pricing-cross-tool-authoring-v2-run-03`
- bridge status: `ready`
- execution status: `complete`
- execution cells: 165

Cell status inventory:

| Cell status | Count | Meaning |
|---|---:|---|
| `pass` | 49 | Pytest passed. For the reference oracle, this admits the suite for mutant interpretation. For mutants, this means the mutant survived that suite. |
| `fail` | 94 | Pytest failed. For mutants on reference-passing suites, this is a mutant kill. |
| `excluded` | 22 | All targets for the two reviewed suite exclusions. |

Reference-oracle status:

| Suite run | Vendor | Reference oracle | S4 status |
|---|---|---|---|
| `pricing-cross-tool-authoring-v2-run-01` | OpenAI | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-02` | Anthropic | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-03` | Anthropic | `fail` | unresolved bridge seam |
| `pricing-cross-tool-authoring-v2-run-05` | OpenAI | `excluded` | reviewed suite over-specification |
| `pricing-cross-tool-authoring-v2-run-10` | Anthropic | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-12` | Google | `excluded` | reviewed suite over-specification |
| `pricing-cross-tool-authoring-v2-run-13` | Anthropic | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-14` | OpenAI | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-15` | Google | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-16` | OpenAI | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-19` | Google | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-23` | OpenAI | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-24` | Anthropic | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-26` | Google | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-27` | Google | `pass` | evidence-producing |

Reference status by vendor:

| Suite-author vendor | Reference pass | Reference fail | Reviewed exclusion |
|---|---:|---:|---:|
| Anthropic | 4/5 | 1/5 | 0/5 |
| Google | 4/5 | 0/5 | 1/5 |
| OpenAI | 4/5 | 0/5 | 1/5 |

## Disposition impact

The original 9-failure result should not be used for bias interpretation. The
review found that six rows failed because the bridge harness attempted a
non-callable `_Client` path for suites whose `run_all` contract was callable or
bound-invoker based. Those rows now pass the reference oracle.

The two reviewed exclusions are:

- `pricing-cross-tool-authoring-v2-run-05` (OpenAI): over-specifies
  price-on-request output shape by expecting numeric-line detail fields on a POA
  response line.
- `pricing-cross-tool-authoring-v2-run-12` (Google): over-specifies
  `reduction.percent_total` by folding fixed-amount reductions into an
  equivalent percentage.

The remaining blocker is:

- `pricing-cross-tool-authoring-v2-run-03` (Anthropic): declares a flattened
  decimal-string response seam and short enum aliases that the current bridge
  does not yet normalize. This is not counted as mutant evidence and should not
  be treated as a generated-suite semantic exclusion without a separate bridge
  policy decision.

## Mutant evidence from reference-passing suites

Only suites that pass the reference oracle contribute mutant evidence. After
disposition, 12 suites are reference-passing.

| Suite run | Vendor | Mutants killed | Mutants survived |
|---|---|---:|---:|
| `pricing-cross-tool-authoring-v2-run-01` | OpenAI | 6 | 4 |
| `pricing-cross-tool-authoring-v2-run-02` | Anthropic | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-10` | Anthropic | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-13` | Anthropic | 8 | 2 |
| `pricing-cross-tool-authoring-v2-run-14` | OpenAI | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-15` | Google | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-16` | OpenAI | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-19` | Google | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-23` | OpenAI | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-24` | Anthropic | 8 | 2 |
| `pricing-cross-tool-authoring-v2-run-26` | Google | 5 | 5 |
| `pricing-cross-tool-authoring-v2-run-27` | Google | 7 | 3 |

Vendor averages among reference-passing suites:

| Vendor | Reference-passing suites | Average mutant kills |
|---|---:|---:|
| Anthropic | 4 | 7.50/10 |
| Google | 4 | 6.50/10 |
| OpenAI | 4 | 6.75/10 |

## Mutant-level detection among reference-passing suites

Detected means the mutant target failed while the same suite passed the
reference oracle.

| Mutant target | Anthropic detected | Google detected | OpenAI detected |
|---|---:|---:|---:|
| `round-half-up-for-half-even` | 4 | 1 | 2 |
| `round-down-for-half-even` | 1 | 2 | 0 |
| `sum-for-cascade` | 4 | 4 | 4 |
| `cascade-for-sum` | 4 | 4 | 4 |
| `fixed-before-percent` | 4 | 2 | 3 |
| `candidate-any-positive` | 4 | 4 | 4 |
| `float-arithmetic` | 0 | 1 | 0 |
| `round-intermediate` | 1 | 2 | 2 |
| `clamp-fixed-overrun` | 4 | 2 | 4 |
| `price-on-request-total` | 4 | 4 | 4 |

Strongly detected mutant classes across all three vendors:

- cascade/sum strategy inversion
- candidate-selection positivity/lower-than-unit behavior
- price-on-request total inclusion

Weak or uneven detection classes:

- `float-arithmetic`
- `round-intermediate`
- `round-down-for-half-even`
- `round-half-up-for-half-even` for Google-authored suites

## Bias-audit interpretation

Current evidence still does not support marking the audit bias-cleared, because
S4 remains blocked by run 03. But the corrected disposition removes the strongest
prior OpenAI-specific concern: OpenAI is no longer 0/5 reference-passing.

What the evidence supports:

1. The three-vendor authoring batch is complete, reconciled, and normalized.
2. The reviewed S4 bridge can execute the v2 suite-author artifacts after the
   callable-seam harness correction.
3. Reference admission is now balanced across vendors: Anthropic, Google, and
   OpenAI each have 4/5 reference-passing suite-author rows.
4. The two reviewed suite exclusions are not vendor-concentrated: one OpenAI and
   one Google row are excluded.
5. Among reference-passing suites, all three vendors produce meaningful mutant
   evidence, with average kills in a relatively narrow range.

What the evidence does not prove:

1. It does not prove the audit is fully bias-cleared, because run 03 remains
   unresolved.
2. It does not prove vendor equivalence; the sample is still small and S4 is an
   instrument-quality gate, not a final statistical bias test.
3. It does not prove all semantic mutant classes are adequately covered.

The defensible current conclusion is that reviewer disposition substantially
reduced the apparent vendor skew. The remaining acceptance blocker is an
engineering/policy decision for run 03's declared bridge seam, not a broad
OpenAI/Gemini/Claude bias signal.

## Recommended next steps

1. Decide the run 03 bridge policy:
   - implement reviewed support for flattened decimal-string response seams and
     short enum aliases, then rerun S4; or
   - classify that seam as unsupported and mark run 03 not executable under S4.
2. If bridge support is implemented, add unit coverage for:
   - bare decimal-string response binding,
   - short enum alias normalization,
   - no regression of dict-shaped Amount suites.
3. Rerun S4 after the run 03 decision.
4. Only after S4 reaches a terminal reviewed state should the audit move toward
   final acceptance/signoff language.
