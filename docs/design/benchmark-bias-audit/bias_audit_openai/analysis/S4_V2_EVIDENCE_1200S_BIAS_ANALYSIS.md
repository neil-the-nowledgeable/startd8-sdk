# S4 v2 Evidence 1200s Bias Analysis

Date: 2026-07-05
Batch: `pricing-cross-tool-authoring-v2-evidence-1200s`
Validated branch commit: `6077c044 audit: admit v2 S4 bridge contract aliases`
Base: `faef9d1f Merge pull request #92 from neil-the-nowledgeable/codex/authoring-prompt-current-workdir`

Source artifacts:

- `.startd8/bias-audit-store/pricing-cross-tool-authoring-v2-evidence-1200s/reconciliation-report.json`
- `.startd8/bias-audit-store/pricing-cross-tool-authoring-v2-evidence-1200s/intake-ledger.json`
- `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-committed-v2-controls/s4-preflight.json`
- `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-committed-v2-controls/mutant_kill_matrix.csv`
- `analysis/s4-pre-registration-v2-evidence-1200s.json`
- `analysis/s4-suite-dispositions-v2-evidence-1200s.json`

## Executive summary

The real 30-run authoring batch completed and was promoted cleanly:

- authoring execution: 30/30 completed
- reconciliation: 30/30 accepted
- intake normalization: 30/30 accepted
- suite-author artifacts admitted to S4: 15
- reviewed bridge execution: completed across 165 cells

The S4 bridge itself is now runnable against the v2 batch, but the S4 result is
blocked because 9 of 15 suite-author artifacts fail the reference oracle. This
is a material audit finding. It means the batch is not yet bias-cleared or
instrument-cleared for acceptance.

The strongest cross-vendor signal is in reference-oracle admission:

| Suite-author vendor | Reference-passing suites | Reference-failing suites |
|---|---:|---:|
| Anthropic | 3/5 | 2/5 |
| Google | 3/5 | 2/5 |
| OpenAI | 0/5 | 5/5 |

This is evidence of a vendor-correlated suite-authoring gap in this batch. It is
not, by itself, proof of intentional or inherent model bias. The immediate
interpretation is narrower: the OpenAI/Codex suite-author outputs did not produce
S4-reference-admissible suites under the reviewed bridge and canonical oracle,
while Anthropic and Google produced some admissible suites.

## S4 execution status

Committed S4 rerun:

- `s4-preflight.json` status: `blocked`
- errors: 9
- bridge status: `ready`
- execution status: `complete`
- execution cells: 165

Cell status inventory:

| Cell status | Count | Meaning |
|---|---:|---|
| `fail` | 141 | Pytest failed. For the reference oracle, this blocks the suite. For mutants, this is a mutant kill only if the same suite passed the reference oracle. |
| `pass` | 24 | Pytest passed. For the reference oracle, this admits the suite for mutant interpretation. For mutants, this means the mutant survived that suite. |

Reference-oracle status:

| Suite run | Vendor | Reference oracle |
|---|---|---|
| `pricing-cross-tool-authoring-v2-run-01` | OpenAI | `fail` |
| `pricing-cross-tool-authoring-v2-run-02` | Anthropic | `fail` |
| `pricing-cross-tool-authoring-v2-run-03` | Anthropic | `fail` |
| `pricing-cross-tool-authoring-v2-run-05` | OpenAI | `fail` |
| `pricing-cross-tool-authoring-v2-run-10` | Anthropic | `pass` |
| `pricing-cross-tool-authoring-v2-run-12` | Google | `fail` |
| `pricing-cross-tool-authoring-v2-run-13` | Anthropic | `pass` |
| `pricing-cross-tool-authoring-v2-run-14` | OpenAI | `fail` |
| `pricing-cross-tool-authoring-v2-run-15` | Google | `pass` |
| `pricing-cross-tool-authoring-v2-run-16` | OpenAI | `fail` |
| `pricing-cross-tool-authoring-v2-run-19` | Google | `pass` |
| `pricing-cross-tool-authoring-v2-run-23` | OpenAI | `fail` |
| `pricing-cross-tool-authoring-v2-run-24` | Anthropic | `pass` |
| `pricing-cross-tool-authoring-v2-run-26` | Google | `pass` |
| `pricing-cross-tool-authoring-v2-run-27` | Google | `fail` |

## Reference-failure themes

The failing suites are not random S4 infrastructure failures. The bridge ran,
loaded the suites, and received pytest outcomes. The dominant failure classes
are suite contract or canonical-output-shape mismatches:

- OpenAI runs 01, 05, 14, 16, and 23 fail on expected `Amount` object shape where
  the canonical target returns decimal strings such as `"12.00"` or `"8.00"` for
  amount fields.
- Anthropic run 02 exposes a `run_all` target-resolution contract mismatch.
- Anthropic run 03 fails through a combination of decimal handling and invalid
  argument signaling behavior.
- Google run 12 expects dict-style amount objects where the canonical target
  returns decimal strings.
- Google run 27 exposes callable-adapter mismatch failures across validation
  cases.

These failures should be dispositioned as suite-reference incompatibilities
before any vendor-quality comparison is treated as final.

## Mutant evidence from reference-passing suites

Only suites that pass the reference oracle can be interpreted for mutant kills.
In this committed rerun, 6 suites are reference-passing.

| Suite run | Vendor | Mutants killed | Mutants survived |
|---|---|---:|---:|
| `pricing-cross-tool-authoring-v2-run-10` | Anthropic | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-13` | Anthropic | 8 | 2 |
| `pricing-cross-tool-authoring-v2-run-15` | Google | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-19` | Google | 7 | 3 |
| `pricing-cross-tool-authoring-v2-run-24` | Anthropic | 8 | 2 |
| `pricing-cross-tool-authoring-v2-run-26` | Google | 5 | 5 |

Vendor averages among reference-passing suites:

| Vendor | Reference-passing suites | Average mutant kills |
|---|---:|---:|
| Anthropic | 3 | 7.67/10 |
| Google | 3 | 6.33/10 |
| OpenAI | 0 | n/a |

OpenAI has no mutant-kill score here because all OpenAI suite-author rows fail
the reference oracle. Treating those rows as zero-kill rows would be incorrect;
they are reference-blocked rows.

## Mutant-level detection among reference-passing suites

Detected means the mutant target failed while the same suite passed the
reference oracle.

| Mutant target | Anthropic detected | Google detected | OpenAI detected |
|---|---:|---:|---:|
| `round-half-up-for-half-even` | 3 | 0 | n/a |
| `round-down-for-half-even` | 1 | 1 | n/a |
| `sum-for-cascade` | 3 | 3 | n/a |
| `cascade-for-sum` | 3 | 3 | n/a |
| `fixed-before-percent` | 3 | 2 | n/a |
| `candidate-any-positive` | 3 | 3 | n/a |
| `float-arithmetic` | 0 | 1 | n/a |
| `round-intermediate` | 1 | 2 | n/a |
| `clamp-fixed-overrun` | 3 | 1 | n/a |
| `price-on-request-total` | 3 | 3 | n/a |

The reference-passing suites detect most semantic mutant classes, but detection
is weak for `float-arithmetic` and mixed for `round-intermediate`. That suggests
future suite-authoring prompts should more explicitly require decimal arithmetic
and intermediate-rounding adversarial cases.

## Bias-audit interpretation

Current evidence does not support accepting the audit as bias-cleared.

What the evidence supports:

1. The three-vendor authoring batch is complete, reconciled, and normalized.
2. The reviewed S4 bridge can execute the v2 suite-author artifacts.
3. The S4 outcome is vendor-correlated at the reference-oracle gate:
   OpenAI/Codex is 0/5 reference-passing, while Anthropic and Google are each
   3/5 reference-passing.
4. Among reference-passing suites, Anthropic and Google both produce meaningful
   mutant-kill evidence, with Anthropic stronger in this run.

What the evidence does not prove:

1. It does not prove model-level or vendor-intent bias.
2. It does not prove OpenAI/Codex cannot author good suites.
3. It does not prove Anthropic or Google suites are fully adequate; both still
   have reference failures and surviving mutants.

The defensible conclusion is that this batch found a real cross-tool acceptance
gap that must be reviewed before final audit acceptance.

## Recommended next steps

1. Open reviewer disposition on the 9 reference-oracle failures, grouped by
   failure class:
   - amount object vs decimal string expectations,
   - callable adapter/target-resolution mismatch,
   - invalid argument signaling behavior,
   - decimal parsing and arithmetic assumptions.
2. Decide whether each failing suite is:
   - invalid and excluded from S4 evidence,
   - repairable by a reviewed mechanical bridge/template normalization, or
   - evidence of a prompt/template ambiguity that requires rerunning a new
     pre-registered batch.
3. Do not merge an acceptance report that labels the audit bias-cleared until
   the reference-failure dispositions are reviewed and signed off.
4. Add a small follow-up prompt/template patch that makes the required response
   shape and callable bridge contract explicit before the next real paid batch.
5. If dispositions materially change the admitted suite set, rerun S4 and
   regenerate this report from the updated `s4-preflight.json` and
   `mutant_kill_matrix.csv`.
