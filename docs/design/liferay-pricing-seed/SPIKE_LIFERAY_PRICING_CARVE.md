# Spike: Carving a Liferay-derived pricing seed for the Summer 2026 benchmark

**Status:** Spike complete (read-only research + contract sketch). Feeds the
`/reflective-requirements` pass that follows.
**Date:** 2026-06-17
**Branch:** `feat/liferay-pricing-seed`
**Context:** Evaluate Liferay Commerce as a source of *additive hardened-tier* benchmark seeds
(see `docs/design/benchmark-task-difficulty/`). Phased plan agreed with the user:
Phase 1 = gRPC-translated additive seeds into the existing harness (no harness changes);
Phase 2 = REST/HTTP behavioral lane + Liferay-native, then evaluate a multi-service target.
This spike covers **Phase 1, first seed**.

---

## Verdict: VIABLE — as a *calculator*, not the *engine*

Liferay's pricing splits into two layers. The spike's central finding is the boundary between them:

- **Resolution layer (deeply DB-stateful — NOT carve-able):** which price list applies, which
  discounts are eligible (account → channel → orderType hierarchy walks), coupon usage-limit
  counters, address → tax-rate lookup, price-list discovery. This is `CommerceContext` + hierarchy
  traversal.
- **Arithmetic layer (pure function — the seed):** level resolution → chain-vs-addition strategy
  → promo-min selection → ×quantity → tax conversion. Liferay's delivery `Price` DTO already
  serializes the result, so there is a natural request/response shape to translate.

**Carve rule:** move *all resolution upstream* and pass resolved entries/discounts/rates in as
parameters. With that boundary the service is **fully deterministic with zero DB**, dropping
straight into the existing single-file gRPC harness in Phase 1 **with no harness changes**.

The single residual non-determinism (multi-currency exchange rates) is eliminated by pinning a
single currency with no conversion.

### Why this is a good benchmark seed

Richer and more discriminating than any Online Boutique service: 4-level discounts, a
chain-vs-addition strategy flag, a tax/discount-ordering flag, a max-discount cap, promo-min
selection, and BigDecimal rounding. Maps onto hardened-tier **Axis C (stringent spec)** and
**Axis B (discriminating suite)**.

---

## Source-verified Liferay facts (the basis for the carve)

All from `github.com/liferay/liferay-portal` (master) + Liferay Learn docs.

- **Result model** `CommerceProductPrice` carries two parallel ladders — a net (tax-exclusive) set
  and a `…WithTaxAmount` (tax-inclusive) set: `unitPrice`, `unitPromoPrice`, `finalPrice` (×qty),
  `discountValue`, `taxValue`, and the parallel `…WithTaxAmount` getters.
- **Discount value** `CommerceDiscountValue(amount, percentage, BigDecimal[] percentages)` — the
  `percentages` array is the **4 per-level** resolved percentages.
- **4 discount levels** `level1..level4`; `usePercentage`; type `percentage` | `fixed-amount`;
  `maximumDiscountAmount` cap. For `fixed-amount`, only level1 participates.
- **Stacking is a system config** `CommercePricingConfiguration.commerceDiscountApplicationStrategy()`:
  - **Chain (multiplicative):** `for each level: discounted -= discounted * level/100` (each level
    applies to the running, already-discounted amount). *Default install.*
  - **Addition (additive):** `discounted = price - price * (Σ levels)/100` (levels summed, applied
    once to the original).
- **Promo-min selection:** promo price replaces unit price as the base iff it exists, is `> 0`, and
  is **lower** than the unit price (or unit price is POA).
- **Tax/discount ordering is a channel flag** `CommerceChannel.isDiscountsTargetNetPrice()`:
  - `true` (default): discount the **net** price, then add tax for the with-tax ladder.
  - `false`: convert to **gross** (tax-inclusive) first, discount the gross, then strip tax back to net.
- **Headless surface:** `headless-commerce-admin-pricing` is **CRUD-only** (manages price lists /
  discounts / tiers — no compute endpoint). The *computed* price is returned by the **delivery**
  APIs (`headless-commerce-delivery-catalog` / `-cart`), scoped by channel + authenticated account.
  The delivery `Price` DTO exposes `price`, `promoPrice`, `discount`, `discountPercentage`,
  `discountPercentageLevel1..4`, `finalPrice`. → **This DTO is the natural shape to translate.**

### Minimal deterministic input set (what must be parameters, not DB lookups)
SKU id + quantity + UoM + `calculateTax`; **resolved** unit price + tier bands + promo price + POA
flag; **pre-filtered eligible** discounts (level1..4, usePercentage, type, max cap); discount
application strategy (chain | addition); currency (code, scale, rounding mode); **resolved** tax
rate + `discountsTargetNetPrice` + price-display type. Everything else (account/channel/order
context, eligibility hierarchy, usage-limit counters, address→rate resolution, price-list discovery)
is resolved upstream.

---

## The `.proto` sketch

```proto
syntax = "proto3";
package startd8.bench.pricing.v1;

// All money/quantities are decimal STRINGS ("29.97"), never floats —
// determinism requires exact decimal arithmetic + explicit rounding.
// (Faithful to Liferay's BigDecimal; a float impl will fail the rounding cases.)

service PricingService {
  // Prices a cart of ALREADY-RESOLVED line items. Price-list selection,
  // discount eligibility, coupon validation, and address->tax-rate resolution
  // are performed UPSTREAM. This service is a pure calculator.
  rpc PriceCart(PriceCartRequest) returns (PriceCartResponse);
}

enum DiscountStrategy { DISCOUNT_STRATEGY_UNSPECIFIED = 0; CHAIN = 1; ADDITION = 2; }
enum DiscountKind     { DISCOUNT_KIND_UNSPECIFIED = 0; PERCENTAGE = 1; FIXED_AMOUNT = 2; }
enum RoundingMode     { ROUNDING_MODE_UNSPECIFIED = 0; HALF_UP = 1; HALF_EVEN = 2; }

message Currency { string code = 1; uint32 scale = 2; RoundingMode rounding = 3; }

message Discount {
  DiscountKind kind = 1;
  repeated string levels = 2;          // level1..level4; % for PERCENTAGE, abs for FIXED_AMOUNT (level1 only)
  string maximum_discount_amount = 3;  // "" = uncapped
}

message LineItem {
  string sku = 1;
  string quantity = 2;
  string unit_price = 3;               // resolved net unit list price
  string promo_price = 4;              // "" = none
  bool   price_on_application = 5;     // POA: no public price
  repeated Discount discounts = 6;     // already filtered for eligibility
  string tax_rate = 7;                 // resolved rate as percent, e.g. "20"
}

message PriceCartRequest {
  repeated LineItem items = 1;
  DiscountStrategy strategy = 2;
  Currency currency = 3;
  bool calculate_tax = 4;
  bool discounts_target_net_price = 5; // true: discount net then +tax; false: gross then discount
}

message DiscountValue { string amount = 1; string percentage = 2; repeated string percentages = 3; }

message PricedLineItem {
  string sku = 1;
  string unit_price = 2;
  string unit_promo_price = 3;
  string final_price = 4;                       // net, x quantity, after discount
  DiscountValue discount_value = 5;
  string tax_value = 6;
  string final_price_with_tax_amount = 7;
  DiscountValue discount_value_with_tax_amount = 8;
  bool   price_on_application = 9;
}

message PriceCartResponse {
  repeated PricedLineItem items = 1;
  string subtotal_final_price = 2;
  string subtotal_final_price_with_tax_amount = 3;
}
```

---

## Ground-truth assertions (hand-authored — proving the suite is feasible)

| # | What it pins | Input | Asserted output |
|---|---|---|---|
| G1 | Sanity | qty 2 × `10.00`, no discount, tax off | `final_price=20.00` |
| G2 | Promo-min selection | unit `10.00`, promo `8.00`; 2nd item promo `12.00` | item1 `final=8.00`; item2 promo ignored → `10.00` |
| **G3** | **Chain vs Addition** (strategy discriminator) | unit `100.00`, PERCENTAGE levels `[10,10]` | **CHAIN → `81.00`**; **ADDITION → `80.00`** |
| **G4** | **Rounding-mode boundary** (float-impl killer) | unit `0.25`, 50% off → raw `0.125` | **HALF_UP → `0.13`**; **HALF_EVEN → `0.12`** |
| **G5** | **Tax/discount ordering** (fixed-amount divergence) | unit `100.00`, FIXED_AMOUNT `15` off, tax `20%` | **net-target → net `85.00`, w/tax `102.00`**; **gross-target → w/tax `105.00`, net `87.50`** |
| G6 | Max-discount cap | unit `100.00`, 50% off, cap `30` | discount `30.00`, `final=70.00` |
| G7 | POA + invalid input | POA item; `quantity="-1"`; `DISCOUNT_STRATEGY_UNSPECIFIED` | POA → `price_on_application=true`, no numeric price; negative qty / unspecified strategy → `INVALID_ARGUMENT` |

G3/G4/G5 are the real discriminators — they separate a model that *reasons about the spec* from one
that pattern-matches a generic "apply a discount". None required a DB, address book, or coupon table —
confirming the carve.

### What I deliberately could NOT (and should not) assert
Everything in the resolution layer — price-list discovery, discount eligibility hierarchy, coupon
usage limits, address→tax-rate. By design these are **upstream parameters**, not service behavior.
That is the boundary, not a gap.

---

## Caveat to carry into requirements

This seed measures **arithmetic precision from a stringent spec** — a slightly different skill axis
than Online Boutique's "implement a gRPC service faithful to a proto". That is a *feature* (it
broadens what the benchmark discriminates), but it means the contamination story rests on the
business-logic semantics, not the contract shape. The Liferay field names
(`discountPercentageLevel1..4`, `finalPrice`) are verbatim on GitHub, so the **FR-47 rename pass is
mandatory**; the chain-vs-addition + tax-ordering + cap *semantics* are Liferay-specific and will not
survive into a renamed contract from memory. Derive-and-transform holds.

---

## Open spec decisions for the `/reflective-requirements` pass

1. **Default rounding mode** and whether the seed pins one or parameterizes it (G4 needs both to discriminate).
2. **One seed or two:** support both CHAIN and ADDITION in a single service (flag-driven), or split
   into two seeds? (G3 is the discriminator either way.)
3. **Error taxonomy:** exact gRPC status codes for invalid quantity, unspecified strategy, malformed
   decimal, level-count > 4, negative price.
4. **Language pinning** for the first seed — recommend Node or Python (proven offline runtime
   closure), not Java (heaviest harness surface + most-contaminated Liferay representation).
5. **FR-47 rename map** — concrete neutral renaming of the Liferay-verbatim field names.
6. **Scope of the cart:** single line item vs multi-line subtotal roll-up (affects suite breadth).
7. **Tax model fidelity:** single flat rate per line (spike assumption) vs multiple tax categories.
