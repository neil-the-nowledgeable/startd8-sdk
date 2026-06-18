# Pricing Candidate Contract Rationale

## Field and Message Naming Rationale

The contract uses neutral calculator names: `QuotationArithmetic`, `Evaluate`, `ItemInput`, `ReductionInput`, and `ItemResult`. Monetary fields use generic words such as `base`, `candidate`, `chosen`, `settled`, and `reduction` to avoid carrying source-system names or prior seed contract names into this proposal.

`candidate_unit_amount` represents an optional lower-price candidate without naming it after any particular promotion concept. `quote_only` represents price-on-application behavior in benchmark-neutral terms. `ReductionInput` and `ReductionReport` use "reduction" rather than source-specific discount field names.

Money is represented by `Amount`, a structured decimal string plus ISO-style currency code. Quantities and percentages are also decimal strings. This preserves exact decimal behavior while keeping the proto independent of a runtime language or numeric library.

## FIXED Item Mapping

- `FIXED-001`: The request includes already-resolved item amounts, candidate amounts, reductions, quantity, strategy, and rounding policy. No lookup keys or external resolution fields are present.
- `FIXED-002`: `ItemResult` represents base unit amount, candidate unit amount, chosen unit amount, settled unit and line amounts, reduction amount, quantity, and `quote_only`. Tax-specific counterpart fields are omitted because S2 scope defers tax.
- `FIXED-003`: `ReductionReport` contains `amount`, `combined_rate`, and `applied_rates`.
- `FIXED-004`: `EvaluateRequest.discount_mode` selects runtime discount behavior.
- `FIXED-005`: `ReductionInput.rate_steps` carries ordered percentage levels. The contract rationale limits this repeated field to at most four entries.
- `FIXED-006`: `ItemInput.candidate_unit_amount`, `ItemResult.candidate_unit_amount`, and `ItemResult.candidate_used` express the promotional candidate concept.
- `FIXED-007`: `ItemInput.quote_only`, `ItemResult.quote_only`, and `EvaluateResponse.contains_quote_only` express price-on-application behavior.
- `FIXED-008`: Decimal values are strings in `Amount.decimal`, `ItemInput.quantity`, `ReductionInput.rate_steps`, `ReductionReport.combined_rate`, and `ReductionReport.applied_rates`.
- `FIXED-009`: The proto can be embedded in the existing benchmark seed envelope as the service contract artifact.
- `FIXED-010`: The proto defines one gRPC service with one RPC.

## OPEN Item Decisions

- `OPEN-001`: Chosen service name is `QuotationArithmetic`; RPC name is `Evaluate`; messages and fields use neutral calculator vocabulary.
- `OPEN-002`: Money uses `Amount { string decimal, string currency_code }`. Quantity and percentage values use decimal strings.
- `OPEN-003`: Rounding is explicit through `RoundingRule`. If omitted or unspecified, implementations should round final monetary outputs to scale `2` using `ROUNDING_MODE_HALF_EVEN` and should not round after each reduction.
- `OPEN-004`: Percentage levels are represented by `ReductionInput.rate_steps` and are ordered. Each `REDUCTION_KIND_RATE` reduction may contain one to four percentage strings. `REDUCTION_KIND_UNIT_AMOUNT` subtracts a unit amount after rate reductions in the order supplied.
- `OPEN-005`: `DISCOUNT_MODE_CHAINED` applies rate steps sequentially to the remaining amount. `DISCOUNT_MODE_SUMMED` adds rate steps into one aggregate rate before applying it. `DISCOUNT_MODE_UNSPECIFIED` defaults to chained behavior. Unknown enum values should be rejected by the service as invalid input.
- `OPEN-006`: A candidate unit amount is used only when present, positive, in the same currency as the base unit amount, and lower than the base unit amount. Otherwise the base unit amount is used.
- `OPEN-007`: Tax handling is a primary pilot non-goal. The proto has no tax fields and requires no tax calculation.
- `OPEN-008`: Discount cap behavior is a primary pilot non-goal. The proto has no cap fields and requires no cap calculation or validation.
- `OPEN-009`: Invalid input should be reported with gRPC `INVALID_ARGUMENT`: malformed decimal strings, negative or zero quantity, missing currency for numeric lines, currency mismatch, unspecified reduction kind, too many rate steps, rate steps on a unit-amount reduction, missing unit amount for a unit-amount reduction, numeric amount fields on `quote_only` lines, and unsupported strategy or rounding enum values.
- `OPEN-010`: The pilot covers multiple line items. Response subtotals aggregate numeric lines only and set `contains_quote_only` when any item is quote-only.
- `OPEN-011`: Outputs include unit amounts, line amounts, reduction summary, candidate usage, quantity echo, request item reference, numeric subtotals, and quote-only markers. Tax breakdowns and cap details are omitted.
- `OPEN-012`: Runtime language and startup command are not specified by this contract.

## Known Omissions

Tax calculation, tax-inclusive mirrors, discount caps, customer eligibility, price-list discovery, coupon usage validation, account or channel state, stored tax rates, implementation code, and test cases are out of scope for this primary pilot proto.

The proto cannot enforce decimal parsing, maximum four rate steps, exact rounding defaults, or cross-field validation by itself. Those rules must be stated in the benchmark requirements that accompany this contract.
