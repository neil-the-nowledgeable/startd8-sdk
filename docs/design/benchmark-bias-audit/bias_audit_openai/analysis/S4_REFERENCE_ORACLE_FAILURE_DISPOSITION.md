# S4 Reference-Oracle Failure Disposition

Date: 2026-06-30  
Batch: `pricing-cross-tool-authoring-v1`  
Runner branch: `codex/s4-audit-store-intake`  
Runner commit: `d1eae7ba audit(s4): implement reviewed bridge executor`

## Summary

The reviewed S4 executor bridge ran under no-egress isolation and blocked on four
reference-oracle failures:

- `pricing-cross-tool-authoring-v1-run-03`
- `pricing-cross-tool-authoring-v1-run-10`
- `pricing-cross-tool-authoring-v1-run-13`
- `pricing-cross-tool-authoring-v1-run-24`

Disposition: S4 remains blocked. These rows cannot be used as mutant evidence
until the reference-oracle failures are resolved. The failures separate into two
categories:

1. A promoted reference-oracle decimal grammar defect: exponent/scientific
   decimal strings such as `1e3` are accepted, while the non-Claude implementer
   checklist requires rejecting float-literal forms.
2. A suite over-specification in run 24: the suite expects price-on-request
   response lines to include numeric-line detail fields that the canonical cases
   do not require.

## Dispositions

| Run | Author vendor | Failing reference-oracle checks | Disposition | Required action |
|---|---:|---|---|---|
| `pricing-cross-tool-authoring-v1-run-03` | `anthropic` | `invalid_decimal_float_literal` expects `INVALID_ARGUMENT` for exponent-form decimal input, but the promoted reference oracle accepts it. | Reference-oracle defect, not bridge defect. Do not count as suite failure until oracle grammar is adjudicated/fixed. | Fix the promoted oracle decimal parser to reject exponent/float-literal strings, re-run oracle gate review, then re-run S4. |
| `pricing-cross-tool-authoring-v1-run-10` | `anthropic` | `malformed_decimal_exponent_invalid` expects `INVALID_ARGUMENT`, but the promoted reference oracle accepts exponent-form decimal input. | Reference-oracle defect, not bridge defect. Do not count as suite failure until oracle grammar is adjudicated/fixed. | Same as above. |
| `pricing-cross-tool-authoring-v1-run-13` | `anthropic` | `invalid_decimal_scientific` expects `INVALID_ARGUMENT`, but the promoted reference oracle accepts scientific notation. | Reference-oracle defect, not bridge defect. Do not count as suite failure until oracle grammar is adjudicated/fixed. | Same as above. |
| `pricing-cross-tool-authoring-v1-run-24` | `anthropic` | `err_malformed_decimal_exponent` expects `INVALID_ARGUMENT`, but the promoted reference oracle accepts exponent-form decimal input. It also expects POA response lines to include `promotion_applied` and `reduction`, while canonical cases expect POA lines to echo `line_key`, `quantity`, and `price_on_request` only. | Mixed. Decimal failure is a reference-oracle defect. POA shape failure is suite over-specification relative to canonical cases and checklist. | Fix/adjudicate oracle decimal grammar first. After that, run 24 should remain non-admissible for S4 unless the POA output-shape expectation is independently accepted; generated suite repair is not allowed under the S4 plan. |

## Evidence

### Decimal exponent acceptance

The non-Claude implementer checklist requires decimal validation to reject
float-literal forms:

- `oracle/NON_CLAUDE_IMPLEMENTER_GUIDE.md`: behavior 1 says to reject `NaN`,
  `Inf`, currency symbols, grouping separators, and float literals.

The promoted reference oracle does not currently reject exponent notation before
calling `Decimal(value)`:

- `oracle/reference_oracle.py`: `_parse_decimal` rejects empty values, whitespace,
  some forbidden characters, and non-finite values, but does not reject `e`/`E`.

This explains the shared failure pattern:

- run 03: `invalid_decimal_float_literal`
- run 10: `malformed_decimal_exponent_invalid`
- run 13: `invalid_decimal_scientific`
- run 24: `err_malformed_decimal_exponent`

### Price-on-request output shape

Canonical cases expect POA response lines to echo only:

- `line_key`
- `quantity`
- `price_on_request`

The promoted reference oracle follows that shape for POA lines. Run 24 expects
additional numeric-line detail fields (`promotion_applied`, `reduction`) on POA
lines, causing two reference-oracle failures:

- `ok_price_on_request_excluded_from_totals`
- `ok_all_poa_no_currency_required`

That is a generated-suite expectation mismatch, not a bridge failure.

## Gate consequence

Per the S4 pre-registration and analysis plan:

- A suite contributes mutant evidence only if it passes the reference oracle.
- Harness or oracle-reference failures are not mutant kills.
- Generated suites must not be repaired or normalized after admission.

Therefore the current S4 result remains fail-closed. Do not promote S4 analysis
as accepted until the decimal grammar issue is fixed/adjudicated and S4 is
re-run. If the oracle is fixed, runs 03/10/13 should be re-evaluated. Run 24
requires separate POA-shape disposition and should remain excluded from S4
evidence unless that expectation is accepted by independent review.

## Recommended next steps

1. Patch `oracle/reference_oracle.py` decimal parsing to reject exponent notation
   (`e`/`E`) and other float-literal forms explicitly.
2. Add/extend oracle tests for exponent-form decimal rejection.
3. Re-run the oracle validation gate and obtain the required non-Claude
   re-review signoff.
4. Re-run `scripts/run_cross_tool_bias_s4.py --execute-reviewed-bridge`.
5. If only run 24 remains blocked, record run 24 as non-admissible S4 evidence
   because its POA output-shape expectation over-specifies the canonical case.
