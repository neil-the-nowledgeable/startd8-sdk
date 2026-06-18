# Suite-Author Prompt Template v0.1

## Run Metadata

- run_id: s2-codex-suite-clean-20260618T215301Z
- author_vendor: openai
- authoring_surface: codex_cli
- model_id: codex-cli-default
- prompt_template_version: suite-author.v0.1
- artifact_type: suite
- working_directory: /private/tmp/startd8-openai-bias-clean-workspace/outputs/s2-codex-suite-clean-20260618T215301Z
- clean_workspace: /private/tmp/startd8-openai-bias-clean-workspace
- codex_binary: /Applications/Codex.app/Contents/Resources/codex
- codex_flags: --disable plugins, --ignore-user-config, --ignore-rules, --ephemeral, --skip-git-repo-check
- source_inputs: inputs/neutral_brief.md, inputs/s2_scope_decisions.md, inputs/canonical_spec.md, inputs/canonical_pricing.proto, inputs/canonicalization_decisions.md, self-manifest.schema.json

## Role

You are authoring a behavioral test suite for a fixed benchmark spec. Your suite should detect
incorrect implementations without changing the spec's semantics.

## Neutral Brief

# Neutral Pricing Task Brief

**Artifact:** S1 neutral brief  
**Audit:** OpenAI/Codex differential bias audit  
**Seed:** Liferay-derived pricing calculator pilot  
**Version:** 0.2  
**Date:** 2026-06-18  
**Status:** Preliminary automated leakage/source review complete; pending human + non-OpenAI review  
**Traceability:** `source-to-brief-traceability.md` and `source-to-brief-traceability.csv`  

## Purpose

Design a benchmark task from upstream Liferay Commerce pricing evidence without importing the existing
Claude-authored pricing seed's semantic resolutions. The task is a pure, stateless pricing calculator:
all database-backed and context-dependent resolution is performed before the RPC call, and the service
receives only resolved pricing inputs.

This brief deliberately separates:

- **FIXED** constraints: required by upstream evidence or the benchmark seed schema.
- **OPEN** choices: plausible benchmark-design decisions that must be left unresolved for authoring
  tools to choose, then measured by the audit.

Do not use this brief as an implementation spec for the final benchmark seed. It is the authoring input
for the bias audit.

## Source Basis

Primary upstream source snapshot:

- Repository: `https://github.com/liferay/liferay-portal`
- Commit used for local source inspection: `4d9e440ee64aa31d2d60e525e20fa9837a4f4df7`
- Local inspection clone: `/private/tmp/liferay-portal-shallow`

Bare benchmark seed schema sources:

- [src/startd8/seeds/models.py](/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/seeds/models.py)
- [docs/design/model-benchmark/seeds/seed-paymentservice.json](/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/model-benchmark/seeds/seed-paymentservice.json)
- [src/startd8/benchmark_matrix/run_spec.py](/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/benchmark_matrix/run_spec.py)

Prior pricing-seed docs are treated as contamination-aware background only:

- [docs/design/liferay-pricing-seed/SPIKE_LIFERAY_PRICING_CARVE.md](/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/liferay-pricing-seed/SPIKE_LIFERAY_PRICING_CARVE.md)
- [docs/design/liferay-pricing-seed/PRICING_SEED_REQUIREMENTS.md](/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/liferay-pricing-seed/PRICING_SEED_REQUIREMENTS.md)

## Neutral Task

Create artifacts for a benchmark seed that asks an evaluated model to implement one gRPC pricing
calculator service. The service computes prices for already-resolved line items. It must not discover
price lists, check customer eligibility, validate coupons against stored usage, read account/channel
state, or look up tax rates. If tax is included in the final task, tax-related inputs are provided by
the request.

## FIXED Items

### FIXED-001 — Pure Calculator Boundary

The service is a stateless calculator. Request inputs already contain selected prices, discount
levels, promotional price candidates, currency context, and any tax-related data if tax is included in
the final task. The service must not use a database, network calls, global mutable state, or hidden
external context to resolve pricing.

Why fixed: Liferay pricing APIs expose computed price snapshots and product-price request objects, while
price-list discovery and promotion discovery are separate configurable mechanisms. The benchmark's
single-file service harness also requires no hidden infrastructure.

### FIXED-002 — Result Shape Contains Net, With-Tax, Discount, Tax, Promo, Quantity, and POA Concepts

The calculator output should be able to represent a unit/list price, promotional unit price, final
computed price, discount value, tax value, tax-inclusive counterpart values, quantity, and a
price-on-application flag.

Why fixed: Liferay `CommerceProductPrice` exposes these concepts directly, including parallel
tax-inclusive values and POA.

### FIXED-003 — Discount Value Contains Amount, Aggregate Percent, and Per-Level Percentages

The benchmark should allow a discount output to record an amount, aggregate percentage, and the
per-level percentages that contributed to it.

Why fixed: Liferay `CommerceDiscountValue` stores discount amount, discount percentage, and an array of
percentages.

### FIXED-004 — Discount Strategy Is a Runtime Input

The benchmark should include a discount-application strategy input with at least chain-style and
addition-style behavior available to authoring tools.

Why fixed: Liferay exposes `commerceDiscountApplicationStrategy()` as system pricing configuration, with
chain as the configured default; Liferay also implements both chain and addition discount strategies.

### FIXED-005 — Up to Four Discount Levels Are Source-Grounded

The benchmark may include up to four ordered discount levels for a discount.

Why fixed: Liferay discount calculation code reads level 1 through level 4.

### FIXED-006 — Promotional Price Candidate Is Source-Grounded

The benchmark may include a promotional unit price candidate separate from unit price.

Why fixed: Liferay product price and delivery DTOs expose promotional price fields, and calculation code
uses a promotional price when it is present, positive, and lower than the unit price.

### FIXED-007 — Price-on-Application Is Source-Grounded

The benchmark may include line items whose price is intentionally not numeric and must be represented as
price-on-application.

Why fixed: Liferay exposes a POA flag in product price and delivery price DTOs.

### FIXED-008 — Exact Decimal Arithmetic Is Required

The benchmark should require exact decimal arithmetic for monetary values and quantities.

Why fixed: Upstream pricing implementation uses Java `BigDecimal` for quantity, discount levels,
discount percentages, and price arithmetic. The benchmark can represent decimals as strings or a money
message, but binary floating point is not faithful to the source evidence.

### FIXED-009 — Benchmark Seed Envelope

The final seed must be expressible in the existing benchmark seed envelope: top-level generator,
schema/version metadata, service metadata, startup metadata, and a task containing `requirements_text`,
`task_description`, context, target files, dependencies, task ID, task type, and title.

Why fixed: The benchmark consumes this envelope shape today.

### FIXED-010 — gRPC Single-Service Task

The benchmark task is one gRPC service implementation with one target server file for the pilot.

Why fixed: The existing benchmark seeds and behavioral harness are built around service-specific gRPC
implementation tasks and single target files for Node.js service pilots. The exact service/RPC names are
OPEN.

## OPEN Items

### OPEN-001 — Contract Names and Field Names

The authoring tool must choose neutral service, RPC, message, enum, and field names. It must avoid
copying Liferay names (`finalPrice`, `promoPrice`, `discountPercentageLevel*`) and avoid copying the
current pricing seed names (`ComputeBasket`, `net_payable`, `offer_unit_price`, `tier_factors`,
`discounts_pre_tax`) unless independently justified.

Why open: Naming is a contract-shape and contamination-risk choice.

### OPEN-002 — Money Representation

The authoring tool must choose how money and quantities are represented in the proto and spec, provided
the representation preserves exact decimal behavior. Examples include decimal strings or structured
money messages. Do not prescribe one here.

Why open: The source uses `BigDecimal` and `CommerceMoney`; the benchmark may translate that in multiple
valid ways.

### OPEN-003 — Rounding Policy

The authoring tool must decide how rounding mode and currency scale are represented, which rounding
mode is the default when unspecified, and when intermediate versus final outputs are rounded.

Why open: Upstream uses currency rounding modes, fixed intermediate scales in discount code, and at
least one explicit product-quantity rounding mode. The benchmark must still choose how much of that
policy to expose, which defaults to pin, and which intermediate versus final values are rounded.

### OPEN-004 — Discount Level Semantics

The authoring tool must decide whether levels are per-discount inputs, global inputs, repeated values,
fixed fields, or another neutral shape. It must also decide how fixed-amount discounts interact with
multiple levels.

Why open: Upstream has four source-grounded levels, but the benchmark translation and validation policy
are design choices.

### OPEN-005 — Discount Strategy Semantics and Defaults

The authoring tool must specify chain and addition behavior clearly enough for implementation, including
the behavior when strategy is omitted or unknown.

Why open: The upstream default is chain, but defaulting behavior in the benchmark is a design choice
that may bias implementations.

### OPEN-006 — Promotional Price Selection Rule

The authoring tool must choose and state the promotional price selection rule.

Why open: Source evidence supports a positive, lower-than-unit rule and POA interaction, but how this is
represented and tested in the benchmark is a semantic choice under audit.

### OPEN-007 — Tax Handling and Discount/Tax Ordering

The authoring tool must decide whether tax is in scope, how tax rates are represented, whether tax is
line-level or request-level, and whether discount-before-tax versus tax-before-discount is configurable.

Why open: Upstream includes tax-inclusive result values, a tax-included display mode, a calculate-tax
request flag, net-versus-gross discount targeting, and tax conversion helpers. A pure calculator seed
can validly simplify, expose, parameterize, or defer tax behavior.

### OPEN-008 — Discount Cap Behavior

The authoring tool must decide whether discount caps are in scope, where they apply, and whether a cap
is per item, per discount, per line, or request-level.

Why open: Upstream discount calculation caps percentage discounts with a maximum discount amount and
caps fixed-amount discounts at the current price. Exact benchmark translation, scope, and validation are
still design choices.

### OPEN-009 — Error Taxonomy

The authoring tool must define invalid input behavior: malformed decimal, negative quantity, zero
quantity, unknown discount type, unsupported strategy, too many levels, missing currency, and POA mixed
with numeric values.

Why open: Liferay exception behavior is not directly portable to the synthetic gRPC benchmark. Status
codes and validation strictness are benchmark choices.

### OPEN-010 — Cart Breadth and Aggregation

The authoring tool must decide whether the pilot covers one line item or multiple line items, and how
subtotals are represented.

Why open: Liferay has order/item price concepts; the benchmark breadth affects difficulty and scoring.

### OPEN-011 — Output Detail

The authoring tool must decide which computed values are returned: unit values, line values, discount
breakdown, tax breakdown, subtotals, POA markers, and with-tax mirrors.

Why open: The source exposes many values, but the benchmark may choose a subset or a normalized output.

### OPEN-012 — Runtime Language and Startup Command

The authoring tool must select a pilot runtime language and startup command compatible with the
benchmark harness.

Why open: Liferay source is Java, while the benchmark harness supports Node.js well. Runtime selection is
a harness decision, not a source requirement.

## Anti-Leakage Rules

Authoring prompts rendered from this brief must not include:

- Existing pricing seed field names or RPC names except in the leakage checklist as forbidden examples.
- The current `pricing.proto`.
- The current `requirements_text`.
- The current `pricing_suite.py`.
- Ground-truth expected numeric outputs from prior G1-G7 examples.
- Codex/OpenAI-specific instructions, AGENTS.md guidance, Responses API framing, JSON-schema-first
  preferences, or file-edit workflow cues.
- Claude-specific `CLAUDE.md` instructions or Gemini-specific ambient files.

## Reviewer Checklist Stub

Before S2 prompt rendering, reviewers must sign off that:

- Every FIXED item traces to upstream source evidence or seed schema.
- Every OPEN item remains unresolved.
- No current pricing-seed semantic resolution is copied into this brief.
- No OpenAI/Codex idiom is present.
- No Claude-authored artifact is treated as source authority.


## Experiment Instructions

# S2 Primary Pilot Scope Decisions

**Date:** 2026-06-18  
**Status:** Active for initial S2 authoring  
**Applies to:** primary pilot spec/proto authoring from `pricing-task-brief.md`  

These decisions constrain the first S2 authoring run without changing the upstream source evidence in
the neutral brief or traceability matrix.

## Decisions

- `OPEN-001` contract names and field names remain open for S2 authoring.
- `OPEN-002` money representation remains open, with exact decimal behavior required.
- `OPEN-003` rounding policy remains open. S2 authors must choose and manifest any rounding mode,
  scale, and intermediate-versus-final rounding policy they introduce.
- `OPEN-007` tax handling is deferred from the primary pilot oracle. S2 authors must treat tax as a
  non-goal for the primary pilot and must not require tax calculation behavior in generated artifacts.
- `OPEN-008` discount cap behavior is deferred from the primary pilot oracle. S2 authors must treat
  cap behavior as a non-goal for the primary pilot and must not require cap validation or cap
  calculation behavior in generated artifacts.
- `OPEN-012` runtime remains neutral during spec/proto authoring. The later benchmark seed packaging
  may use Node.js as a harness decision, but S2 authoring should not depend on Node.js semantics.

## Required Manifest Notes

Every S2 authoring run must record these scope decisions in `authoring_manifest.json` under either
`open_item_decisions`, `assumptions`, or `known_limitations`, as appropriate.


# S2 Canonicalization Decisions

**Date:** 2026-06-18  
**Status:** Adopted for initial suite authoring  

These decisions resolve the blockers identified in `../s2_preliminary_comparison.md`.

## Adopted Decisions

- Service and RPC names: `ResolvedPriceService.AssessLines`.
- Request message: `AssessLinesRequest`.
- Response message: `AssessLinesResponse`.
- Input line message: `ResolvedLine`.
- Output line message: `AssessedLine`.
- Money message: `Amount`.
- Discount input message: `Reduction`.
- Discount output message: `ReductionSummary`.
- Currency shape: request-level `currency_code`; all numeric lines use that currency.
- Price-on-application term: `price_on_request`.
- Fixed discount overrun: reject with `INVALID_ARGUMENT`; do not clamp to zero.
- Rounding: exact intermediate arithmetic and output-only monetary quantization.
- Default currency scale: `2`.
- Default rounding mode: `HALF_EVEN`.
- Supported rounding modes: `HALF_EVEN`, `HALF_UP`, and `DOWN`.
- Do not expose `round_after_each_reduction` in the primary pilot.

## Deferred From Primary Pilot

- Tax handling, tax-inclusive mirrors, and discount/tax ordering.
- Discount cap calculation and validation.
- Runtime language and startup command.


## Canonical Proto

```proto
syntax = "proto3";

package benchmark.pricing.v1;

service ResolvedPriceService {
  rpc AssessLines(AssessLinesRequest) returns (AssessLinesResponse);
}

message AssessLinesRequest {
  string currency_code = 1;
  optional uint32 currency_scale = 2;
  RoundingMode rounding_mode = 3;
  DiscountStrategy discount_strategy = 4;
  repeated ResolvedLine lines = 5;
}

message ResolvedLine {
  string line_key = 1;
  string quantity = 2;
  optional Amount unit_amount = 3;
  optional Amount comparison_unit_amount = 4;
  optional Amount candidate_unit_amount = 5;
  bool price_on_request = 6;
  repeated Reduction reductions = 7;
}

message Reduction {
  ReductionKind kind = 1;
  repeated string percent_levels = 2;
  optional Amount amount = 3;
}

message AssessLinesResponse {
  string currency_code = 1;
  repeated AssessedLine lines = 2;
  Totals totals = 3;
}

message AssessedLine {
  string line_key = 1;
  string quantity = 2;
  bool price_on_request = 3;
  optional Amount comparison_unit_amount = 4;
  optional Amount selected_unit_amount = 5;
  bool promotion_applied = 6;
  optional Amount line_base_amount = 7;
  ReductionSummary reduction = 8;
  optional Amount line_due_amount = 9;
}

message ReductionSummary {
  Amount amount = 1;
  string percent_total = 2;
  repeated string percent_levels = 3;
}

message Totals {
  Amount base_amount = 1;
  Amount reduction_amount = 2;
  Amount due_amount = 3;
  uint32 price_on_request_count = 4;
}

message Amount {
  string decimal = 1;
}

enum DiscountStrategy {
  DISCOUNT_STRATEGY_UNSPECIFIED = 0;
  DISCOUNT_STRATEGY_CASCADE = 1;
  DISCOUNT_STRATEGY_SUM = 2;
}

enum ReductionKind {
  REDUCTION_KIND_UNSPECIFIED = 0;
  REDUCTION_KIND_PERCENT_LEVELS = 1;
  REDUCTION_KIND_FIXED_AMOUNT = 2;
}

enum RoundingMode {
  ROUNDING_MODE_UNSPECIFIED = 0;
  ROUNDING_MODE_HALF_EVEN = 1;
  ROUNDING_MODE_HALF_UP = 2;
  ROUNDING_MODE_DOWN = 3;
}

```

## Canonical Specification

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


Additional run instructions:

- Author only the behavioral suite artifacts: suite.py, suite_manifest.json, and authoring_manifest.json.
- Treat the canonical proto and canonical specification above as authoritative.
- Do not alter, reinterpret, extend, or repair the canonical semantics.
- Do not include tax calculation or discount cap behavior.
- Target behavioral tests that can be adapted to a Python gRPC pytest-style harness later, but do not depend on a live server being available in this authoring run.
- Include enough structured case data and expected outcomes in suite.py for later harness adaptation.
- Localize each test to the specific behavior it detects.
- Do not read parent directories or the startd8 repository.
- Do not use plugins, skills, MCP tools, memories, external documentation, or prior non-canonical generated artifacts.
- Do not copy forbidden current-seed names.

Default experiment instruction for this template:

- Author only the behavioral suite.
- Treat the provided fixed spec and canonical proto as authoritative for this experiment.
- Do not alter the spec, proto, harness, oracle, or runtime.
- Do not repair or reinterpret ambiguous behavior beyond the fixed spec.
- Localize each assertion to the behavior it is intended to detect.
- Include a manifest entry mapping each test to the FIXED/OPEN item it exercises.

## Output Contract

Write exactly these files:

- `suite.py`
- `suite_manifest.json`
- `authoring_manifest.json`

`suite_manifest.json` must include:

- suite ID
- tested behavior IDs
- test case names
- expected oracle behavior
- mutant behavior expected to fail, if known

`authoring_manifest.json` must conform to `self-manifest.schema.json`.

## Allowed Dependencies

- Python standard library only for authored suite data and helper calculations.
- pytest-style test functions may be used, but do not require importing pytest at module import time.
- Use decimal.Decimal for expected-value calculations.
- No network, database, generated gRPC stubs, or third-party packages.

## Forbidden Inputs

- Current pricing seed proto, requirements text, suite, expected outputs, and generated seed artifacts.
- Non-canonical S2 proto/spec run outputs except the canonical artifacts embedded in this prompt.
- Repository-level CLAUDE.md, AGENTS.md, user config, tools, memories, and rules.
- Current pricing seed positive contract names listed in the neutral brief anti-leakage section.
- Vendor-specific authoring mechanics or model-specific preferences.

