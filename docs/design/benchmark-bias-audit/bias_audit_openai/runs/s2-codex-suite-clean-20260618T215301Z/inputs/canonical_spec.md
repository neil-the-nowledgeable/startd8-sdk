# Canonical Resolved Line Price Calculator Specification

## Scope

Implement one stateless gRPC service, `ResolvedPriceService`, with one RPC, `AssessLines`. The service
prices already-resolved line item inputs. It must not discover price lists, resolve promotions, validate
coupon usage, read account or channel state, look up tax rates, use a database, use network calls, rely
on global mutable state, or depend on clock time.

The primary pilot covers exact decimal line pricing, promotional candidate selection, ordered
percentage reductions, fixed amount reductions, request-level discount strategy selection,
price-on-request line handling, output-only rounding, validation, line results, and numeric request
totals.

Tax handling and discount cap behavior are non-goals for the primary pilot.

## Service Behavior

The request contains one or more `ResolvedLine` entries and one request-level `currency_code` for all
numeric lines. Currency conversion is out of scope.

For each non-`price_on_request` line:

1. Parse all decimal strings as exact finite base-10 decimals.
2. Select the unit amount used for arithmetic:
   - Start with `unit_amount`.
   - If `candidate_unit_amount` is present, strictly greater than zero, and strictly less than
     `unit_amount`, use `candidate_unit_amount`.
   - Otherwise use `unit_amount`.
3. Multiply selected unit amount by `quantity` to produce `line_base_amount`.
4. Apply percentage reductions according to request `discount_strategy`.
5. Apply fixed amount reductions after percentage reductions, in request order.
6. Reject the request if a fixed amount reduction would make the remaining line amount negative.
7. Return line and total monetary outputs rounded only at output formatting time.

For `price_on_request` lines:

- Do not perform numeric price arithmetic.
- Do not include numeric price or reduction inputs.
- Echo the line key, quantity, and `price_on_request` marker.
- Exclude the line from numeric totals.
- Increment `totals.price_on_request_count`.

## Input/Output Shape

The canonical proto is `pricing.proto`.

Request-level fields:

- `currency_code`: required if any line is numeric. All numeric line amounts use this currency.
- `currency_scale`: optional non-negative integer. If omitted, use `2`.
- `rounding_mode`: optional enum. If omitted or unspecified, use `HALF_EVEN`.
- `discount_strategy`: optional enum. If omitted or unspecified, use `CASCADE`.
- `lines`: one or more resolved line items.

Line fields:

- `line_key`: required and unique within the request.
- `quantity`: exact decimal string greater than zero.
- `unit_amount`: required for numeric lines; absent for price-on-request lines.
- `comparison_unit_amount`: optional display/list amount for numeric lines.
- `candidate_unit_amount`: optional promotional candidate for numeric lines.
- `price_on_request`: marker for lines without numeric pricing.
- `reductions`: zero or more percentage or fixed amount reductions.

Reduction fields:

- `PERCENT_LEVELS`: one to four ordered percentage strings in `percent_levels`; no `amount`.
- `FIXED_AMOUNT`: one non-negative `amount`; no `percent_levels`.

Response fields:

- One `AssessedLine` per input line, in input order.
- Numeric totals over non-price-on-request lines only.
- `price_on_request_count` for excluded price-on-request lines.

## Calculation Rules

Percentage strings are decimal percent values: `"12.5"` means 12.5 percent.

For `CASCADE`, apply percentage levels sequentially to the remaining line amount. For example, levels
`10` then `5` leave `0.90 * 0.95` of the amount before fixed reductions.

For `SUM`, add percentage levels into one aggregate percent and apply once. For example, levels `10`
then `5` produce a 15 percent reduction before fixed reductions.

Fixed amount reductions subtract from the remaining line amount after percentage reductions. If any
fixed amount reduction would make the remaining line amount negative, the whole request is invalid with
`INVALID_ARGUMENT`. Do not clamp to zero.

`ReductionSummary.amount` is the final total reduction amount for the line.
`ReductionSummary.percent_total` is the effective aggregate percentage represented as a decimal percent.
`ReductionSummary.percent_levels` echoes the ordered percentage levels used for percentage reductions.

## Rounding

Implementations must not use binary floating point for parsing, arithmetic, comparison, or formatting.

All intermediate arithmetic remains exact. Monetary outputs are quantized only when written to the
response:

- Default `currency_scale`: `2`.
- Default `rounding_mode`: `HALF_EVEN`.
- Supported modes: `HALF_EVEN`, `HALF_UP`, and `DOWN`.

Percent output fields are decimal strings with up to six fractional digits, rounded with the selected
rounding mode only if representation requires rounding.

## Validation Behavior

Invalid requests fail the RPC with `INVALID_ARGUMENT`. Tests should assert the status code and behavior,
not exact error-message wording.

Invalid inputs include:

- Empty `lines`.
- Missing or duplicate `line_key`.
- Missing `currency_code` when any numeric line exists.
- Malformed decimal strings, including `NaN`, infinity, currency symbols, grouping separators, or
  binary-float literals.
- Quantity less than or equal to zero.
- Negative `unit_amount`, `comparison_unit_amount`, `candidate_unit_amount`, or fixed reduction amount.
- Numeric line without `unit_amount`.
- `price_on_request` line with `unit_amount`, `comparison_unit_amount`, `candidate_unit_amount`, or
  reductions.
- Percentage reduction with fewer than one or more than four levels.
- Percentage level less than zero or greater than `100`.
- Fixed amount reduction without `amount`.
- Percentage reduction with `amount`.
- Fixed amount reduction with `percent_levels`.
- Fixed amount reduction that would make the remaining line amount negative.
- Unknown reduction kind, discount strategy, or rounding mode.
- Negative `currency_scale`.

## Open Item Decisions

- `OPEN-001`: Canonical names are `ResolvedPriceService.AssessLines`, `AssessLinesRequest`,
  `AssessLinesResponse`, `ResolvedLine`, `AssessedLine`, `Amount`, `Reduction`, and
  `ReductionSummary`.
- `OPEN-002`: Money is `Amount { string decimal }`; quantities and percentages are decimal strings;
  `currency_code` is request-level.
- `OPEN-003`: Output-only rounding; default scale `2`; default mode `HALF_EVEN`; supported modes
  `HALF_EVEN`, `HALF_UP`, and `DOWN`.
- `OPEN-004`: Percentage reductions use one to four ordered levels; fixed reductions are separate
  amount reductions applied after percentage reductions.
- `OPEN-005`: Strategies are `CASCADE` and `SUM`; omitted/unspecified strategy defaults to `CASCADE`;
  unknown strategies are invalid.
- `OPEN-006`: Use a promotional candidate only when present, positive, and lower than the resolved unit
  amount.
- `OPEN-007`: Tax handling is deferred and not represented in the canonical primary-pilot contract.
- `OPEN-008`: Discount cap behavior is deferred; over-large fixed reductions are invalid rather than
  clamped.
- `OPEN-009`: Invalid inputs use gRPC `INVALID_ARGUMENT`.
- `OPEN-010`: The primary pilot covers one or more line items and numeric request totals.
- `OPEN-011`: Outputs include selected unit amount, optional comparison amount, line base amount,
  reduction summary, line due amount, price-on-request markers, and numeric totals.
- `OPEN-012`: Runtime language and startup command remain packaging decisions outside this spec.

## Assumptions

- Inputs are resolved before the RPC call.
- All numeric lines in a request use the request-level currency.
- Proto field presence is used to distinguish absent optional monetary inputs from present zero values.
- Later benchmark packaging will choose runtime language, dependencies, startup command, and seed
  envelope details.

## Non-goals

- Tax calculation, tax-inclusive output mirrors, or discount/tax ordering.
- Discount caps, maximum-discount scopes, or silent clamping.
- Price-list lookup, promotion discovery, coupon eligibility, coupon usage tracking, account/channel
  rules, inventory checks, persistence, or currency conversion.
- Reference implementation, test suite, runtime packaging, or startup metadata.
