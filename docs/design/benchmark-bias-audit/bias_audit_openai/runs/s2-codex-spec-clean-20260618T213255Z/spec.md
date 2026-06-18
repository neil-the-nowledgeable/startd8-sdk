# Resolved Line Price Calculator Specification

## Scope

This benchmark asks an implementer to build one stateless gRPC pricing calculator service for already-resolved line item inputs. The service receives all prices, quantities, discount inputs, promotional candidates, currency metadata, and calculation policy needed for the request. It must not use a database, network call, file-backed lookup, global mutable state, clock-dependent behavior, account context, channel context, coupon history, customer eligibility rules, price-list discovery, or promotion discovery.

The primary pilot covers numeric line pricing, promotional candidate selection, ordered percentage discounts, optional fixed discounts, request-level discount strategy selection, price-on-request line handling, exact decimal arithmetic, validation, line results, and request totals. Tax handling and discount cap behavior are outside this pilot and must not be implemented as required behavior.

## Service Behavior

The service exposes a single RPC, `AssessLines`, on a service named `ResolvedPriceService`. The RPC accepts a request containing one or more resolved line items and returns one result per input line plus request totals for numeric lines.

Each non-POA line is priced as follows:

1. Parse all decimal strings exactly as base-10 decimal values.
2. Select the working unit amount:
   - Start with the resolved unit amount.
   - If a promotional candidate is present, strictly greater than zero, and strictly less than the resolved unit amount, use the promotional candidate as the working unit amount.
   - Otherwise use the resolved unit amount.
3. Multiply the selected working unit amount by quantity to form the line base amount.
4. Apply discounts to the line base amount.
5. Return the discounted line amount, the line discount amount, the aggregate discount percent, per-level percentages used, the selected unit amount, and whether the promotional candidate was selected.

Discount strategy is a runtime request input:

- `CASCADE`: ordered percentage levels are applied one after another to the remaining amount. For levels `10` then `5`, the remaining multiplier is `(1 - 0.10) * (1 - 0.05)`.
- `SUM`: ordered percentage levels are added to one aggregate percentage and applied once to the line base amount. For levels `10` then `5`, the aggregate percentage is `15`.

Fixed discounts are line-level decimal amounts applied after percentage discounts. A fixed discount subtracts from the remaining line amount. Because cap behavior is not in scope, a fixed discount that would make the line amount negative is invalid rather than silently clamped.

If discount strategy is omitted, the service uses `CASCADE`. Unknown strategy values are invalid.

Price-on-request lines do not produce numeric price arithmetic. A POA line result must preserve the line identifier, requested quantity, currency code when present, and a POA marker. POA lines are excluded from numeric request totals. A line marked POA must not include numeric unit, promotional, or discount amount inputs.

## Input/Output Shape

This section defines the required logical contract. A later proto may use equivalent names, but it must preserve these fields and semantics.

Request:

- `currency_code`: required ISO-style currency identifier for numeric requests, such as `USD`.
- `currency_scale`: optional non-negative integer for output quantization. If omitted, use `2`.
- `rounding`: optional enum. Supported values are `HALF_EVEN`, `HALF_UP`, and `DOWN`. If omitted, use `HALF_EVEN`.
- `discount_strategy`: optional enum with `CASCADE` and `SUM`.
- `lines`: one or more resolved line items.

Line item:

- `line_key`: required caller-provided identifier, unique within the request.
- `quantity`: required exact decimal string. Must be greater than zero.
- `unit_amount`: exact decimal string for the resolved unit amount. Required unless `price_on_request` is true.
- `comparison_unit_amount`: optional exact decimal string for the pre-discount unit amount shown for comparison or list purposes.
- `candidate_unit_amount`: optional exact decimal string promotional candidate.
- `price_on_request`: required boolean.
- `discounts`: zero or more line discount entries.

Line discount entry:

- `kind`: enum with `PERCENT_LEVELS` or `FIXED_AMOUNT`.
- `levels`: ordered decimal-string percentages. Required for `PERCENT_LEVELS`; must contain one to four values.
- `amount`: decimal string. Required for `FIXED_AMOUNT`.

Response:

- `currency_code`: copied from the request.
- `lines`: one result per input line in input order.
- `totals`: numeric subtotal fields for all non-POA lines.

Line result:

- `line_key`: copied from the input line.
- `price_on_request`: boolean.
- `quantity`: copied as the normalized exact decimal value.
- `comparison_unit_amount`: present when supplied for a numeric line.
- `selected_unit_amount`: the unit amount used for arithmetic, after promotional selection.
- `promotion_applied`: boolean.
- `line_base_amount`: selected unit amount multiplied by quantity before discounts.
- `line_discount_amount`: total discount amount for the line.
- `discount_percent_total`: effective aggregate percentage represented as a decimal percent.
- `discount_percent_levels`: ordered percentage levels that contributed to the percentage discount calculation.
- `line_due_amount`: final numeric amount after discounts.

Totals:

- `base_amount`: sum of numeric `line_base_amount` values.
- `discount_amount`: sum of numeric `line_discount_amount` values.
- `due_amount`: sum of numeric `line_due_amount` values.
- `poa_line_count`: count of POA lines excluded from numeric totals.

All monetary output fields must be decimal strings quantized to `currency_scale` using the selected rounding mode. Intermediate calculations must retain exact decimal precision and must not be rounded until an output monetary field is produced. Percent output fields are decimal strings with up to six fractional digits, rounded with the selected rounding mode only when needed for representation. Implementations must not use binary floating point for parsing, arithmetic, comparison, or formatting.

## Validation Behavior

Invalid requests must fail the RPC with `INVALID_ARGUMENT`. Implementations should include a field-oriented error message, but tests should rely on status code and behavior rather than exact wording.

Validation rules:

- `lines` must contain at least one item.
- `line_key` is required and must be unique within the request.
- `currency_code` is required when any line is numeric.
- Decimal strings must be syntactically valid base-10 decimals, with no `NaN`, infinity, exponent-only token, currency symbol, grouping separator, or binary-float literal.
- Quantity must be greater than zero.
- Numeric unit amounts and promotional candidates must be zero or greater.
- A numeric line must include `unit_amount`.
- A POA line must not include `unit_amount`, `comparison_unit_amount`, `candidate_unit_amount`, or discount entries.
- `PERCENT_LEVELS` discounts must provide one to four percentage levels.
- Percentage levels must be zero or greater and must not exceed `100`.
- `FIXED_AMOUNT` discounts must provide a non-negative amount.
- A fixed discount that would make a line result negative is invalid.
- Unknown discount kinds, unknown discount strategies, unknown rounding modes, negative currency scale, or malformed decimal fields are invalid.

## Open Item Decisions

- `OPEN-001`: Use neutral names centered on resolved line assessment: `ResolvedPriceService`, `AssessLines`, line keys, selected amounts, and POA markers. This avoids source-specific naming while keeping the contract readable.
- `OPEN-002`: Represent money and quantities as decimal strings plus request currency metadata. This keeps exact decimal behavior independent of any implementation language.
- `OPEN-003`: Default to `HALF_EVEN`, default `currency_scale` to `2`, round only output monetary fields, and keep intermediate arithmetic exact. This is deterministic while avoiding hidden intermediate rounding.
- `OPEN-004`: Model percentage discounts as ordered repeated levels per discount entry, with one to four levels. Fixed discounts are separate entries and apply after percentage discounts.
- `OPEN-005`: Support `CASCADE` and `SUM`, default omitted strategy to `CASCADE`, and reject unknown strategies. The default provides deterministic behavior without requiring a separate configuration source.
- `OPEN-006`: Select a promotional candidate only when it is present, positive, and lower than the resolved unit amount. Return a boolean indicating whether it was selected.
- `OPEN-007`: Tax handling is deferred from the primary pilot. The spec does not require tax calculation, tax inputs, tax outputs, tax-inclusive mirror fields, or tax/discount ordering behavior.
- `OPEN-008`: Discount cap behavior is deferred from the primary pilot. The spec does not require cap validation or cap calculation; fixed discounts that exceed the remaining amount are invalid.
- `OPEN-009`: Use gRPC `INVALID_ARGUMENT` for malformed decimals, missing required fields, unsupported enum values, invalid POA/numeric mixing, zero or negative quantity, too many percentage levels, and negative final line outcomes.
- `OPEN-010`: Cover multiple line items and return request totals over numeric lines, with POA lines counted but excluded from numeric totals.
- `OPEN-011`: Return selected unit amounts, optional comparison unit amounts, line base amounts, discount totals, effective discount percentages, level percentages, final line amounts, POA markers, and numeric request totals.
- `OPEN-012`: Runtime language and startup command remain unspecified in this prose spec. Later benchmark packaging may choose a runtime without changing calculator semantics.

## Assumptions

- The request is already resolved by upstream systems before the RPC call.
- Currency conversion is out of scope; all numeric lines in a request use the request currency.
- Decimal normalization may remove insignificant trailing zeroes for non-money fields, but monetary outputs must follow `currency_scale`.
- The benchmark harness will define proto-level enum numeric values later.

## Non-goals

- Tax calculation, tax validation, tax-inclusive output mirrors, or tax/discount ordering.
- Discount maximum caps, per-item caps, per-line caps, request caps, or silent clamping.
- Price-list lookup, promotion discovery, coupon eligibility, coupon usage tracking, customer/account/channel rules, inventory checks, or persistence.
- A reference implementation, test suite, runtime dependency list, startup command, or service packaging.
- Binary floating point arithmetic.
