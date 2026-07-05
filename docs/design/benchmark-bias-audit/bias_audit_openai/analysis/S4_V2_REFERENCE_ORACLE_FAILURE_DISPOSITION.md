# S4 v2 Reference-Oracle Failure Disposition

Date: 2026-07-05
Batch: `pricing-cross-tool-authoring-v2-evidence-1200s`
Reviewer: Codex

Source runs:

- Original committed rerun:
  `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-committed-v2-controls`
- Corrected bridge-harness rerun:
  `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-disposition-rerun`
- Post-disposition verification rerun:
  `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-after-dispositions`
- Final flattened-seam bridge rerun:
  `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-flattened-seam`

## Summary

The original v2 S4 rerun reported 9 reference-oracle failures. Review found that
6 of those failures were caused by the reviewed bridge harness invoking
`run_all(call=None)` suites with a non-callable `_Client` object before using the
declared callable/bound-invoker seam.

The bridge harness was corrected to use the callable adapter seam for the
supplemental `run_all` check. After rerun, reference-oracle status improved from
6/15 passing to 12/15 passing.

The remaining 3 failures were dispositioned as follows:

| Run | Vendor | Disposition | Gate action |
|---|---|---|---|
| `pricing-cross-tool-authoring-v2-run-03` | Anthropic | Bridge seam gap for flattened decimal-string/enum-alias contract. Do not exclude as generated-suite semantic failure. | Add reviewed bridge support for the declared seam and rerun S4. |
| `pricing-cross-tool-authoring-v2-run-05` | OpenAI | Generated suite over-specifies canonical price-on-request response-line shape. | Exclude from S4 evidence. |
| `pricing-cross-tool-authoring-v2-run-12` | Google | Generated suite over-specifies canonical reduction summary semantics for `percent_total`. | Exclude from S4 evidence. |

The reviewed v2 suite-disposition control now excludes only runs 05 and 12.
After adding reviewed bridge support for run 03's declared flattened decimal
string and short enum-alias seam, S4 completes with 13 reference-passing suites,
2 reviewed exclusions, and no remaining reference failures.

## Original 9-failure disposition

| Run | Vendor | Original failure class | Disposition |
|---|---|---|---|
| `pricing-cross-tool-authoring-v2-run-01` | OpenAI | `run_all` called with non-callable `_Client`; fallback then exposed amount-shape mismatch through the wrong supplemental path. | Cleared by bridge-harness correction. Counts as reference-passing after rerun. |
| `pricing-cross-tool-authoring-v2-run-02` | Anthropic | `run_all` rejected non-callable `_Client` with suite-local configuration error. | Cleared by bridge-harness correction. Counts as reference-passing after rerun. |
| `pricing-cross-tool-authoring-v2-run-03` | Anthropic | Flattened decimal-string response seam and enum aliases were not honored by the bridge binding. | Cleared by reviewed flattened-seam bridge support. Counts as reference-passing after final rerun. |
| `pricing-cross-tool-authoring-v2-run-05` | OpenAI | Price-on-request line expected numeric-line fields such as `promotion_applied`/`reduction`. | Excluded from S4 evidence as suite over-specification. |
| `pricing-cross-tool-authoring-v2-run-12` | Google | Expected `reduction.percent_total == "30.333333"` for a case with fixed reductions, treating fixed amounts as equivalent percentage. | Excluded from S4 evidence as suite over-specification. |
| `pricing-cross-tool-authoring-v2-run-14` | OpenAI | `run_all` supplemental path used the wrong adapter shape. | Cleared by bridge-harness correction. Counts as reference-passing after rerun. |
| `pricing-cross-tool-authoring-v2-run-16` | OpenAI | `run_all` supplemental path used the wrong adapter shape. | Cleared by bridge-harness correction. Counts as reference-passing after rerun. |
| `pricing-cross-tool-authoring-v2-run-23` | OpenAI | `run_all` supplemental path used the wrong adapter shape. | Cleared by bridge-harness correction. Counts as reference-passing after rerun. |
| `pricing-cross-tool-authoring-v2-run-27` | Google | `run_all` called with non-callable `_Client`, producing callable-adapter failures. | Cleared by bridge-harness correction. Counts as reference-passing after rerun. |

## Corrected bridge-harness result

After changing the supplemental `run_all` bridge test to use the callable adapter
seam, the corrected rerun produced:

- status: `blocked`
- bridge status: `ready`
- execution status: `complete`
- execution cells: 165
- reference oracle: 12 pass, 3 fail

Reference status by vendor before suite exclusions:

| Vendor | Reference pass | Reference fail |
|---|---:|---:|
| Anthropic | 4/5 | 1/5 |
| Google | 4/5 | 1/5 |
| OpenAI | 4/5 | 1/5 |

## Reviewed exclusions

### `pricing-cross-tool-authoring-v2-run-05`

Disposition: `exclude_from_s4_evidence`

Reason class: `suite_over_specifies_canonical_output_shape`

Normalized SHA-256:
`309f4298b3c6e987106ba164c0f6bbe704f181de0848b3fe7d85cb102042806c`

Evidence:

- Failing case: `price_on_request_line_excluded_from_numeric_totals`
- Failure: generated suite expects a price-on-request response line to include
  numeric-line fields such as `promotion_applied` and `reduction`.
- Reviewed canonical behavior: price-on-request lines are excluded from numeric
  assessment output beyond the canonical POA echo fields and totals count.

Conclusion: this is a generated-suite over-specification. Do not repair the
generated suite; exclude it from S4 mutant evidence.

### `pricing-cross-tool-authoring-v2-run-12`

Disposition: `exclude_from_s4_evidence`

Reason class: `suite_over_specifies_canonical_output_shape`

Normalized SHA-256:
`8520ff6e1049d244d3ce9d74587c3ef363f1a266a813d5ffd36550a9248854ab`

Evidence:

- Failing case: `test_fixed_amount_reductions`
- Failure: generated suite expects `reduction.percent_total == "30.333333"` for
  a case with a 20% percentage reduction followed by fixed-amount reductions.
- Reviewed canonical behavior: `percent_total` summarizes percentage-level
  reductions; fixed-amount reductions are reported in `reduction.amount`, not
  folded into an equivalent percentage.

Conclusion: this is a generated-suite over-specification. Do not repair the
generated suite; exclude it from S4 mutant evidence.

## Resolved bridge seam: `pricing-cross-tool-authoring-v2-run-03`

Disposition: bridge seam gap resolved by reviewed mechanical bridge support.

Normalized SHA-256:
`0b7d1dcb57f838271db7ae4871e09f1eb65c54526fd8d5debf70069f9cec9347`

Evidence:

- The suite manifest declares a flattened seam:
  monetary values, quantities, and percentages are plain decimal strings.
- The manifest also declares enum aliases such as `PERCENT_LEVELS`, `FIXED_AMOUNT`,
  `HALF_UP`, and `DOWN`.
- The prior bridge bound `bind_invoker` to a native dict-returning adapter and
  did not normalize those short enum aliases into canonical proto enum names.
- The reference oracle therefore rejected otherwise ok cases with errors such as
  `unknown reduction kind` and `unknown rounding mode`, and the suite could also
  receive dict-shaped amounts where it expected decimal strings.

Conclusion: run 03 should not be excluded as a generated-suite semantic failure.
The bridge now reads the admitted suite manifest's `bridge_contract`, normalizes
declared short enum aliases, and returns flattened decimal strings only when the
declared contract calls for that seam. That preserves dict-shaped Amount support
for other suites while admitting run 03's declared bridge contract.

## Post-disposition verification

After adding reviewed exclusions for runs 05 and 12, S4 was rerun with:

- result root:
  `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-after-dispositions`
- status: `blocked`
- only remaining error:
  `S4 bridge reference oracle failed:pricing-cross-tool-authoring-v2-run-03`

Matrix status after dispositions:

| Status | Count |
|---|---:|
| Reference pass | 12 |
| Reference fail | 1 |
| Reference excluded | 2 |

Reference status by vendor after dispositions:

| Vendor | Reference pass | Reference fail | Excluded |
|---|---:|---:|---:|
| Anthropic | 4/5 | 1/5 | 0/5 |
| Google | 4/5 | 0/5 | 1/5 |
| OpenAI | 4/5 | 0/5 | 1/5 |

## Final flattened-seam verification

After adding reviewed bridge support for run 03, S4 was rerun with:

- result root:
  `/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v2-evidence-1200s/s4-results-flattened-seam`
- status: `complete`
- errors: `[]`

Final matrix status:

| Status | Count |
|---|---:|
| Reference pass | 13 |
| Reference fail | 0 |
| Reference excluded | 2 |

Final reference status by vendor:

| Vendor | Reference pass | Reference fail | Excluded |
|---|---:|---:|---:|
| Anthropic | 5/5 | 0/5 | 0/5 |
| Google | 4/5 | 0/5 | 1/5 |
| OpenAI | 4/5 | 0/5 | 1/5 |

## Gate consequence

The 9 original reference-oracle failures are dispositioned and S4 now reaches a
terminal complete state. Runs 05 and 12 remain reviewed exclusions. Run 03 is
admitted as reference-passing under reviewed bridge support for its declared
flattened decimal-string / short enum-alias seam.
