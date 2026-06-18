# S2 Preliminary Comparison

**Date:** 2026-06-18  
**Compared runs:**

- `runs/s2-codex-proto-clean-20260618T205742Z`
- `runs/s2-codex-spec-clean-20260618T213255Z`

## Convergence

The independently authored proto and prose spec converged on these decisions:

- Use exact decimal strings rather than binary floating point.
- Defer tax handling from the primary pilot.
- Defer discount cap behavior from the primary pilot.
- Support multiple line items and numeric request totals.
- Include a runtime discount strategy with chain/cascade and sum/addition behavior.
- Default omitted discount strategy to chain/cascade.
- Use final-output rounding with scale 2 and half-even default.
- Treat invalid input as `INVALID_ARGUMENT`.
- Keep runtime language and startup command unspecified during S2 authoring.

## Divergence

The runs diverged or varied in these areas:

- Contract names differ: proto chose `QuotationArithmetic.Evaluate`; spec chose
  `ResolvedPriceService.AssessLines`.
- POA wording differs: proto chose `quote_only`; spec chose `price_on_request`.
- Currency shape differs: proto puts currency on each `Amount`; spec uses request-level currency
  metadata.
- Fixed discount overrun behavior is clearer in the spec: a fixed discount that would make a line
  negative is invalid. The proto rationale omits cap behavior but does not encode this exact validation
  rule in the proto itself.
- Proto includes `round_after_each_reduction`; spec states output-only rounding. This needs adjudication
  before a canonical contract is frozen.

## Recommended Canonicalization Gate

Before suite authoring, choose one canonical answer for:

- service/RPC/message/field names;
- request-level versus amount-level currency;
- POA terminology;
- fixed discount overrun validation;
- whether the final proto should expose `round_after_each_reduction` or require output-only rounding.
