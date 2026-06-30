# S4 Suite-Authoring Analysis Report

Date: 2026-06-30
Batch: `pricing-cross-tool-authoring-v1`
Validated code: `origin/main` at `6459fcb00ce3258ea02dca84979bb1d680d4c18d`
Source artifacts:

- `analysis/s4-results/s4-preflight.json`
- `analysis/s4-results/mutant_kill_matrix.csv`
- `analysis/s4-suite-dispositions.json`

## Executive summary

S4 completed successfully after post-merge validation:

- `s4-preflight.json` status: `complete`
- errors: `[]`
- oracle gate status: `accepted`
- mutant manifest status: `accepted`
- promoted-batch reconciliation status: `accepted`
- reviewed suite-disposition status: `reviewed`

The reviewed S4 bridge produced usable mutant evidence from 4 suites. One suite
(`pricing-cross-tool-authoring-v1-run-24`) was excluded by reviewed disposition
because it over-specified canonical price-on-request output shape. Ten accepted
suite-author artifacts were not executable under the reviewed bridge because they
did not declare a supported adapter/invoker contract.

This report is bounded to S4 suite-authoring instrument evidence. It does not
claim vendor bias, score impact, or overall audit acceptance.

## Admission and execution inventory

The promoted audit store contained 15 accepted `suite_author` artifacts from a
31-row intake ledger. S4 processed those 15 accepted suites as follows:

| Category | Count | Runs |
|---|---:|---|
| Evidence-producing suites | 4 | `run-02`, `run-03`, `run-10`, `run-13` |
| Reviewed exclusions | 1 | `run-24` |
| Accepted but not executable under reviewed bridge | 10 | `run-01`, `run-05`, `run-12`, `run-14`, `run-15`, `run-16`, `run-19`, `run-23`, `run-26`, `run-27-replacement-1` |

Vendor distribution:

| Vendor | Accepted S4 rows | Evidence-producing | Excluded | Not executable |
|---|---:|---:|---:|---:|
| Anthropic | 5 | 4 | 1 | 0 |
| OpenAI | 5 | 0 | 0 | 5 |
| Google | 5 | 0 | 0 | 5 |

Interpretation: executable S4 evidence is concentrated in Anthropic-authored
suites because those suites exposed compatible adapter/invoker contracts. The
OpenAI and Google rows remain accepted intake artifacts, but they do not provide
S4 mutant evidence under the current bridge. This must not be interpreted as a
quality or bias comparison across vendors.

## Cell status summary

The bridge evaluated 165 suite-target cells:

| Cell status | Count | Meaning |
|---|---:|---|
| `pass` | 14 | Suite target execution passed. For reference oracle, this admits the row for mutant interpretation. For mutants, this means the mutant survived that suite. |
| `fail` | 30 | Mutant target failed against a reference-passing suite. In S4 terms, this is mutant detection by that suite. |
| `excluded` | 11 | All targets for run 24 were excluded by reviewed suite disposition. |
| `not_executable` | 110 | Accepted suite did not expose a reviewed bridge-compatible contract. |

There were no remaining reference-oracle failures:

- reference failures: `[]`
- excluded reference row: `pricing-cross-tool-authoring-v1-run-24`

## Evidence-producing suite results

The following suites passed the reference oracle and therefore contribute mutant
evidence:

| Suite | Reference oracle | Mutants detected | Mutants survived |
|---|---|---:|---:|
| `pricing-cross-tool-authoring-v1-run-02` | `pass` | 8 | 2 |
| `pricing-cross-tool-authoring-v1-run-03` | `pass` | 7 | 3 |
| `pricing-cross-tool-authoring-v1-run-10` | `pass` | 7 | 3 |
| `pricing-cross-tool-authoring-v1-run-13` | `pass` | 8 | 2 |

Detected means the mutant column value was `fail` while the same suite passed
the reference oracle. Survived means the mutant column value was `pass`.

## Mutant-level detection summary

Detection across the 4 reference-passing suites:

| Mutant target | Detected by suites | Survived suites | Detection rate |
|---|---:|---:|---:|
| `round-half-up-for-half-even` | 4 | 0 | 4/4 |
| `round-down-for-half-even` | 2 | 2 | 2/4 |
| `sum-for-cascade` | 4 | 0 | 4/4 |
| `cascade-for-sum` | 4 | 0 | 4/4 |
| `fixed-before-percent` | 4 | 0 | 4/4 |
| `candidate-any-positive` | 4 | 0 | 4/4 |
| `float-arithmetic` | 0 | 4 | 0/4 |
| `round-intermediate` | 0 | 4 | 0/4 |
| `clamp-fixed-overrun` | 4 | 0 | 4/4 |
| `price-on-request-total` | 4 | 0 | 4/4 |

Strongly detected mutant classes:

- rounding-mode substitution toward half-up
- cascade/sum strategy inversion
- fixed-before-percent reduction ordering
- candidate-selection positivity/lower-than-unit behavior
- fixed-reduction overrun clamping
- price-on-request total inclusion

Undetected mutant classes in this S4 evidence set:

- `float-arithmetic`
- `round-intermediate`

Interpretation: the four executable suites provide good coverage of many
semantic mutant classes, but they do not detect the decimal-arithmetic and
intermediate-rounding mutants in the current matrix.

## Reviewed exclusion: run 24

Run 24 was excluded from S4 evidence through
`analysis/s4-suite-dispositions.json`.

Disposition:

- `run_id`: `pricing-cross-tool-authoring-v1-run-24`
- `normalized_sha256`: `c28e243e3d863845e74cfd8b9a3cdf3acf662e26e58c9536bc55d94e10d63180`
- reason class: `suite_over_specifies_canonical_output_shape`
- action: `exclude_from_s4_evidence`

Rationale: run 24 expects price-on-request response lines to include numeric-line
detail fields. Canonical cases and the promoted reference oracle require POA
lines to echo `line_key`, `quantity`, and `price_on_request`, while excluding
them from numeric totals. The generated suite was not repaired.

## Limitations

1. S4 currently has evidence-producing rows only for Anthropic-authored suites.
   OpenAI and Google accepted suites were not executable because they lacked a
   reviewed bridge-compatible adapter/invoker contract.
2. Non-executable rows are not failures and not zero-kill rows; they are admitted
   artifacts that cannot provide S4 evidence under the current executor.
3. The matrix uses `pass`/`fail` target outcomes. This report interprets mutant
   `fail` only for suites whose `reference_oracle` cell is `pass`.
4. S4 is an instrument-quality suite-authoring analysis. It is not a vendor-bias
   acceptance verdict and should not be used as one.

## Recommended follow-up

1. Preserve the completed S4 artifacts as the post-merge evidence snapshot.
2. Add S4 reporting/presentation that distinguishes:
   - evidence-producing rows,
   - reviewed exclusions,
   - accepted-but-not-executable rows.
3. For future S4 batches, update suite-authoring prompts/templates to require a
   standard adapter/invoker contract so all vendors can produce executable S4
   evidence.
4. If S4 is intended to support cross-vendor comparison, rerun a new
   pre-registered suite-authoring batch after that adapter contract requirement
   is in place.
