# S4 v2 Evidence 1200s Bias Analysis

Date: 2026-07-05
Batch: `pricing-cross-tool-authoring-v2-evidence-1200s`
Branch: `codex/s4-v2-bridge-aliases`
Base: `faef9d1f Merge pull request #92 from neil-the-nowledgeable/codex/authoring-prompt-current-workdir`

Source artifacts:

- `.startd8/bias-audit-store/pricing-cross-tool-authoring-v2-evidence-1200s/reconciliation-report.json`
- `.startd8/bias-audit-store/pricing-cross-tool-authoring-v2-evidence-1200s/intake-ledger.json`
- `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-flattened-seam/s4-preflight.json`
- `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-flattened-seam/mutant_kill_matrix.csv`
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
- final S4 status: `complete`
- final S4 errors: `[]`

Reviewer disposition of the original 9 reference-oracle failures changed the S4
picture materially:

- 6 failures were bridge-harness artifacts and cleared after the supplemental
  `run_all` check was corrected to use the callable adapter seam.
- 2 failures were generated-suite over-specifications and are now reviewed
  exclusions from S4 evidence.
- 1 failure exposed a declared flattened decimal-string / short enum-alias seam;
  reviewed bridge support was added and the row now passes the reference oracle.

The final S4 evidence no longer supports the earlier OpenAI-specific 0/5
reference-admission concern. Final reference admission is:

| Suite-author vendor | Reference pass | Reference fail | Reviewed exclusion |
|---|---:|---:|---:|
| Anthropic | 5/5 | 0/5 | 0/5 |
| Google | 4/5 | 0/5 | 1/5 |
| OpenAI | 4/5 | 0/5 | 1/5 |

## Final S4 execution status

Final S4 verification:

- `s4-preflight.json` status: `complete`
- errors: `[]`
- bridge status: `ready`
- execution status: `complete`
- execution cells: 165

Cell status inventory:

| Cell status | Count | Meaning |
|---|---:|---|
| `pass` | 53 | Pytest passed. For the reference oracle, this admits the suite for mutant interpretation. For mutants, this means the mutant survived that suite. |
| `fail` | 90 | Pytest failed. For mutants on reference-passing suites, this is a mutant kill. |
| `excluded` | 22 | All targets for the two reviewed suite exclusions. |

Reference-oracle status:

| Suite run | Vendor | Reference oracle | S4 status |
|---|---|---|---|
| `pricing-cross-tool-authoring-v2-run-01` | OpenAI | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-02` | Anthropic | `pass` | evidence-producing |
| `pricing-cross-tool-authoring-v2-run-03` | Anthropic | `pass` | evidence-producing |
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

## Disposition impact

The original 9-failure result should not be used for bias interpretation. Review
found that six rows failed because the bridge harness attempted a non-callable
`_Client` path for suites whose `run_all` contract was callable or
bound-invoker based. Those rows now pass the reference oracle.

The two reviewed exclusions are:

- `pricing-cross-tool-authoring-v2-run-05` (OpenAI): over-specifies
  price-on-request output shape by expecting numeric-line detail fields on a POA
  response line.
- `pricing-cross-tool-authoring-v2-run-12` (Google): over-specifies
  `reduction.percent_total` by folding fixed-amount reductions into an
  equivalent percentage.

The final bridge support added for run 03 is mechanical:

- it reads the admitted `bridge_contract` metadata in the isolated workspace;
- it normalizes declared short enum aliases such as `PERCENT_LEVELS`,
  `FIXED_AMOUNT`, `HALF_UP`, and `DOWN`;
- it returns flattened decimal strings only when the declared contract calls for
  that seam;
- it preserves dict-shaped `{"decimal": "..."}` behavior for other suites.

## Mutant evidence from reference-passing suites

Only suites that pass the reference oracle contribute mutant evidence. After
final disposition and bridge support, 13 suites are reference-passing.

| Suite run | Vendor | Mutants killed | Mutants survived |
|---|---|---:|---:|
| `pricing-cross-tool-authoring-v2-run-01` | OpenAI | 6 | 4 |
| `pricing-cross-tool-authoring-v2-run-02` | Anthropic | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-03` | Anthropic | 7 | 3 |
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
| Anthropic | 5 | 7.40/10 |
| Google | 4 | 6.50/10 |
| OpenAI | 4 | 6.75/10 |

## Mutant-level detection among reference-passing suites

Detected means the mutant target failed while the same suite passed the
reference oracle.

| Mutant target | Anthropic detected | Google detected | OpenAI detected |
|---|---:|---:|---:|
| `round-half-up-for-half-even` | 5 | 1 | 2 |
| `round-down-for-half-even` | 1 | 2 | 0 |
| `sum-for-cascade` | 5 | 4 | 4 |
| `cascade-for-sum` | 5 | 4 | 4 |
| `fixed-before-percent` | 5 | 2 | 3 |
| `candidate-any-positive` | 5 | 4 | 4 |
| `float-arithmetic` | 0 | 1 | 0 |
| `round-intermediate` | 1 | 2 | 2 |
| `clamp-fixed-overrun` | 5 | 2 | 4 |
| `price-on-request-total` | 5 | 4 | 4 |

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

Current S4 evidence reaches a terminal complete state and does not show a
vendor-specific OpenAI/Codex reference-admission failure.

What the evidence supports:

1. The three-vendor authoring batch is complete, reconciled, and normalized.
2. The reviewed S4 bridge can execute the v2 suite-author artifacts.
3. Reference admission is not OpenAI-skewed: Anthropic has 5/5 passing rows,
   while Google and OpenAI each have 4/5 passing rows and one reviewed exclusion.
4. The two reviewed suite exclusions are not concentrated in OpenAI: one OpenAI
   and one Google row are excluded.
5. Among reference-passing suites, all three vendors produce meaningful mutant
   evidence, with average kills in a relatively narrow range.

What the evidence does not prove:

1. It does not prove full vendor equivalence; the sample remains small.
2. It does not prove all semantic mutant classes are adequately covered.
3. It does not by itself complete final audit acceptance; final signoff still
   needs reviewer agreement on the bridge changes, suite exclusions, and mutant
   adequacy limits.

The defensible current conclusion is that the S4 reference-oracle blockers have
been dispositioned and cleared to a terminal complete S4 state. The strongest
remaining limitation is mutant adequacy, especially weak detection of
`float-arithmetic`, `round-intermediate`, and rounding-mode variants.

## Recommended next steps

1. Have the non-Claude reviewers verify:
   - the flattened-seam bridge support is mechanical,
   - the two reviewed exclusions are acceptable,
   - no generated suite was repaired or normalized.
2. Decide whether the surviving/weak mutant classes require prompt/template
   tightening before final audit acceptance.
3. If reviewers accept those limits, prepare the final acceptance/signoff memo
   using the terminal S4 result:
   `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-flattened-seam`.
