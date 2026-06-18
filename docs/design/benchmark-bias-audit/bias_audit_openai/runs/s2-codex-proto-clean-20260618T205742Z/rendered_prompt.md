# Proto-Collection Prompt Template v0.1

## Run Metadata

- run_id: s2-codex-proto-clean-20260618T205742Z
- author_vendor: openai
- authoring_surface: codex_cli
- model_id: codex-cli-default
- prompt_template_version: proto-collection.v0.1
- artifact_type: proto
- working_directory: /private/tmp/startd8-openai-bias-clean-workspace/outputs/s2-codex-proto-clean-20260618T205742Z
- clean_workspace: /private/tmp/startd8-openai-bias-clean-workspace
- codex_binary: /Applications/Codex.app/Contents/Resources/codex
- codex_flags: --disable plugins, --ignore-user-config, --ignore-rules, --ephemeral, --skip-git-repo-check
- source_inputs: inputs/neutral_brief.md, inputs/s2_scope_decisions.md, self-manifest.schema.json

## Role

You are proposing a gRPC contract shape from a neutral source brief. This output is collected only for
divergence analysis and optional contract-shape sensitivity. It is not used in the primary FR-6
score-impact run.

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


Additional run instructions:

- Use only the neutral brief and S2 primary pilot scope decisions embedded in this prompt.
- Treat tax handling and discount cap behavior as non-goals for the primary pilot. Do not require tax calculation, tax fields, cap validation, or cap calculation in the proposed proto.
- Preserve source-grounded concepts only when they remain in scope after the S2 decisions.
- Keep exact decimal behavior expressible. Do not use binary floating point semantics.
- Write the output files in the current working directory.
- Do not read parent directories or the startd8 repository.
- Do not use plugins, skills, MCP tools, memories, or external documentation.
- Do not copy forbidden names except inside a clearly marked anti-leakage explanation if absolutely necessary. Prefer avoiding them entirely.

Default experiment instruction for this template:

- Author only a `.proto` contract and a contract rationale.
- Keep all source-grounded FIXED items expressible.
- Make explicit decisions for every OPEN item your contract resolves.
- Do not copy existing pricing seed names listed as forbidden inputs.
- Do not include implementation code or tests.

## Output Contract

Write exactly these files:

- `pricing_candidate.proto`
- `contract_rationale.md`
- `authoring_manifest.json`

`contract_rationale.md` must include:

- field/message naming rationale
- mapping from FIXED items to proto elements
- OPEN item decisions
- known omissions

`authoring_manifest.json` must conform to `self-manifest.schema.json`.

## Allowed Dependencies

- Protocol Buffers proto3 syntax only.
- No implementation runtime or third-party package dependencies.

## Forbidden Inputs

- Current pricing seed proto, requirements text, suite, expected outputs, and generated seed artifacts.
- Repository-level CLAUDE.md, AGENTS.md, user config, tools, memories, and rules.
- Current pricing seed positive contract names listed in the neutral brief anti-leakage section.
- Vendor-specific authoring mechanics or model-specific preferences.

