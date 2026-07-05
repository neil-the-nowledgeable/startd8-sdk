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

## Summary

The original v2 S4 rerun reported 9 reference-oracle failures. Review found that
6 of those failures were caused by the reviewed bridge harness invoking
`run_all(call=None)` suites with a non-callable `_Client` object before using the
declared callable/bound-invoker seam.

The bridge harness was corrected to use the callable adapter seam for the
supplemental `run_all` check. After rerun, reference-oracle status improved from
6/15 passing to 12/15 passing.

The remaining 3 failures disposition as follows:

| Run | Vendor | Disposition | Gate action |
|---|---|---|---|
| `pricing-cross-tool-authoring-v2-run-03` | Anthropic | Bridge seam gap for flattened decimal-string/enum-alias contract. Do not exclude as generated-suite semantic failure. | Keep S4 blocked until bridge support is added or this seam is explicitly classified not executable. |
| `pricing-cross-tool-authoring-v2-run-05` | OpenAI | Generated suite over-specifies canonical price-on-request response-line shape. | Exclude from S4 evidence. |
| `pricing-cross-tool-authoring-v2-run-12` | Google | Generated suite over-specifies canonical reduction summary semantics for `percent_total`. | Exclude from S4 evidence. |

The reviewed v2 suite-disposition control now excludes only runs 05 and 12.
Post-disposition S4 verification remains blocked only by run 03.

## Original 9-failure disposition

| Run | Vendor | Original failure class | Disposition |
|---|---|---|---|
| `pricing-cross-tool-authoring-v2-run-01` | OpenAI | `run_all` called with non-callable `_Client`; fallback then exposed amount-shape mismatch through the wrong supplemental path. | Cleared by bridge-harness correction. Counts as reference-passing after rerun. |
| `pricing-cross-tool-authoring-v2-run-02` | Anthropic | `run_all` rejected non-callable `_Client` with suite-local configuration error. | Cleared by bridge-harness correction. Counts as reference-passing after rerun. |
| `pricing-cross-tool-authoring-v2-run-03` | Anthropic | Flattened decimal-string response seam and enum aliases are not honored by the current bridge binding. | Remaining blocker. Do not count as suite failure or mutant evidence. |
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

## Remaining blocker: `pricing-cross-tool-authoring-v2-run-03`

Disposition: unresolved bridge seam gap, not an S4 evidence row.

Normalized SHA-256:
`0b7d1dcb57f838271db7ae4871e09f1eb65c54526fd8d5debf70069f9cec9347`

Evidence:

- The suite manifest declares a flattened seam:
  monetary values, quantities, and percentages are plain decimal strings.
- The manifest also declares enum aliases such as `PERCENT_LEVELS`, `FIXED_AMOUNT`,
  `HALF_UP`, and `DOWN`.
- The current bridge binds `bind_invoker` to a native dict-returning adapter and
  does not normalize those short enum aliases into canonical proto enum names.
- The reference oracle therefore rejects otherwise ok cases with errors such as
  `unknown reduction kind` and `unknown rounding mode`, and the suite can also
  receive dict-shaped amounts where it expects decimal strings.

Conclusion: run 03 should not be excluded as a generated-suite semantic failure.
It is blocked by an unsupported but declared bridge seam. The next engineering
decision is either:

1. add reviewed bridge support for flattened decimal-string response seams and
   declared short enum aliases, then rerun S4; or
2. classify that seam as unsupported and mark run 03 not executable under S4.

Because the v2 bridge-contract admission currently accepts this manifest, option
1 is the more internally consistent path.

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

## Gate consequence

The 9 original reference-oracle failures are now dispositioned, but S4 is still
fail-closed because run 03 remains unresolved. Do not mark the audit
bias-cleared until run 03 is either bridge-supported and rerun, or explicitly
classified as not executable by reviewed S4 policy.
