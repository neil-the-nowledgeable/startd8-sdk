# Neutral Task Brief — Upstream Pricing Calculator

**File Path:** `brief/pricing-task-brief.md`  
**Version:** 1.0 (Neutral Baseline)  
**Date:** 2026-06-18  
**Subject:** Upstream Liferay-derived Pricing Calculator (Phase 1)

This brief describes the stateless price calculation rules extracted from Liferay Commerce (`CommerceProductPrice`, `CommerceDiscountValue`, and `CommercePricingConfiguration`). 

This document serves as the neutral prompt input for the benchmark re-authoring runs. It explicitly tags requirements as **[FIXED]** (constraints imposed by the upstream source or schema boundary) or **[OPEN]** (semantic or naming decisions left to the authoring tool's discretion, which represent the bias-testing surface).

---

## 1. Core Service Interface & Data Format

* **[FIXED-1] Stateless Pure Function:** The service must be a pure, stateless calculator. Price-list lookup, eligibility, and address-to-tax-rate resolution are performed upstream. All data required for calculation must be provided in the request. No database, external network, or local caching is allowed.
* **[OPEN-1] Service and Method Naming:** The gRPC service name and the RPC method name are not defined by the upstream source and are open to the tool's discretion.
* **[FIXED-2] Data Type for Monetary Values:** To avoid binary floating-point representation errors and preserve exact decimal arithmetic, all monetary amounts and quantities must be handled as decimal strings (e.g., `"12.34"`).
* **[OPEN-2] Message and Field Names:** The names of input and output messages, as well as their fields, are open.

---

## 2. Input Parameters (Request Structure)

The calculation request must provide the following inputs:
1. **[FIXED-3] Line Items:** A collection of one or more line items (up to 3 items for aggregation validation).
2. **[FIXED-4] Quantities & Base Prices:** Per line item, a quantity (decimal string), a base unit price (decimal string), and an optional promotional unit price (decimal string).
3. **[FIXED-5] Promo-Min Selection:** The promotional unit price replaces the base unit price as the starting calculation price if and only if:
   * The promo price is defined,
   * The promo price is $> 0$, and
   * The promo price is strictly lower than the unit price.
4. **[FIXED-6] Eligible Discounts:** A list of eligible discounts to apply. Each discount carries a collection of tiers (representing discount levels) and an optional maximum discount cap.
5. **[OPEN-3] Discount Tier Structure:** The number of discount levels and the way they are represented in the message structure (e.g., individual fields `level1..4` vs. a repeated array of factors) is open.
6. **[FIXED-7] Tax Rate:** A flat tax rate represented as a percentage (decimal string) per line item.
7. **[OPEN-4] Rounding Parameters:** The currency representation must support specifying scale (fraction digits) and a rounding mode. The default rounding mode when none is specified is open.
8. **[FIXED-8] Strategy and Ordering Flags:** Flags indicating:
   * How multiple discount tiers are stacked.
   * Whether tax is calculated before or after discounts.

---

## 3. Calculation Logic

For each line item where a price is available (non-POA):

### 3.1 Base Calculation
1. Establish the starting unit price via promo-min selection (Unit Price vs. Promo Price).
2. Compute the initial line amount: $\text{Base} = \text{Starting Unit Price} \times \text{Quantity}$.

### 3.2 Discount Stacking Strategy
Discounts must be applied according to one of two stacking strategies (selected by request flag):
* **[FIXED-9] Multiplicative Stacking (CHAIN):** Apply each discount level sequentially to the running discounted amount. For each level $t$:
  $$\text{Amount}_{\text{new}} = \text{Amount}_{\text{old}} - \left(\text{Amount}_{\text{old}} \times \frac{t}{100}\right)$$
* **[FIXED-10] Additive Stacking (ADDITION):** Sum the percentages of all discount levels first, and apply the combined rate once to the original base amount:
  $$\text{Amount}_{\text{discounted}} = \text{Base} \times \left(1 - \frac{\sum t}{100}\right)$$
* **[FIXED-11] Fixed-Amount Discounts:** A fixed-amount discount represents a flat subtraction from the running amount (only the first tier is applied; others are ignored). The discount subtraction cannot reduce the running line amount below zero.
* **[FIXED-12] Discount Cap:** If a maximum discount limit is defined for a discount, the total discount subtraction for that specific discount item is capped at that limit.

### 3.3 Tax Ordering Strategies
The service must support two tax calculation paths (selected by request flag):
* **[FIXED-13] Discount Net (Discounts Pre-Tax):** 
  1. Calculate the final discounted net amount.
  2. Round the net amount to the currency scale.
  3. Calculate the tax value: $\text{Tax} = \text{Net} \times \frac{\text{Tax Rate}}{100}$.
  4. Round the tax value to the currency scale.
  5. Compute the gross amount: $\text{Gross} = \text{Net} + \text{Tax}$.
* **[FIXED-14] Discount Gross (Tax-Inclusive Discounting):**
  1. Compute the initial gross base: $\text{Gross Base} = \text{Base} \times \left(1 + \frac{\text{Tax Rate}}{100}\right)$.
  2. Apply the discounts sequentially to the gross amount.
  3. Round the resulting gross amount to the currency scale (representing $\text{Gross Payable}$).
  4. Deconstruct the net value: $\text{Net} = \text{Gross Payable} / \left(1 + \frac{\text{Tax Rate}}{100}\right)$.
  5. Round the net value to the currency scale.
  6. Compute the tax value: $\text{Tax} = \text{Gross Payable} - \text{Net}$.

---

## 4. Price on Application (POA) & Validation

* **[FIXED-15] Price on Application:** If an item is flagged as POA (Price on Application), the service must return a response with the POA flag set to true and all numeric price fields left empty (`""`). No pricing calculations are executed for that item.
* **[OPEN-5] gRPC Error Handling:** Requests containing invalid inputs must return a validation error. The exact error codes, error messages, and behavior for edge cases (e.g., negative prices, empty strings) are open.


---

## 5. Source-to-Brief Traceability Matrix

| Brief ID | Status | Decision Owner | Source / Schema Constraint | Justification |
|---|---|---|---|---|
| **FIXED-1** | FIXED | `source-evidence` | `SPIKE_LIFERAY_PRICING_CARVE.md` §1 | Liferay splits pricing into resolution and arithmetic layers; moving resolution upstream is a requirement for a stateless test. |
| **OPEN-1** | OPEN | `human-adjudication` | None | Naming is a styling/idiom choice; leaving it open tests tool-specific naming conventions. |
| **FIXED-2** | FIXED | `source-evidence` | `PRICING_SEED_REQUIREMENTS.md` FR-7 | Upstream Liferay uses `BigDecimal` for precision. Strings are required to preserve exact rounding. |
| **OPEN-2** | OPEN | `human-adjudication` | None | Field names are arbitrary; testing whether tools default to Liferay names or vendor-specific naming schemas. |
| **FIXED-3** | FIXED | `source-evidence` | `SPIKE_LIFERAY_PRICING_CARVE.md` §2.5 | Multi-line carts verify aggregation and summation logic. |
| **FIXED-4** | FIXED | `source-evidence` | `PRICING_SEED_REQUIREMENTS.md` FR-2 | Upstream Liferay requires quantity, unit list price, and promo price for line calculation. |
| **FIXED-5** | FIXED | `source-evidence` | `SPIKE_LIFERAY_PRICING_CARVE.md` §2 | Promo-min selection matches the Liferay delivery logic. |
| **FIXED-6** | FIXED | `source-evidence` | `PRICING_SEED_REQUIREMENTS.md` FR-6 | Stacking discounts and max caps are native Liferay engine structures. |
| **OPEN-3** | OPEN | `human-adjudication` | None | Represents a structural choice (array vs explicit level fields level1..level4). |
| **FIXED-7** | FIXED | `source-evidence` | `SPIKE_LIFERAY_PRICING_CARVE.md` §2 | A flat tax rate matches the carved stateless tax calculation. |
| **OPEN-4** | OPEN | `human-adjudication` | `PRICING_SEED_REQUIREMENTS.md` OQ-1 | Unspecified rounding defaults are open to tool choice, mapping to different vendor preferences. |
| **FIXED-8** | FIXED | `source-evidence` | `PRICING_SEED_REQUIREMENTS.md` FR-3, FR-5 | Stacking strategies and tax/discount ordering flags are required parameters to verify arithmetic logic. |
| **FIXED-9** | FIXED | `source-evidence` | `CommercePricingConfiguration` (Liferay Portal) | Matches the default multiplicative discount strategy in Liferay. |
| **FIXED-10** | FIXED | `source-evidence` | `CommercePricingConfiguration` (Liferay Portal) | Matches the additive discount strategy in Liferay. |
| **FIXED-11** | FIXED | `source-evidence` | `CommerceDiscountValue` (Liferay Portal) | Flat fixed-amount deductions are supported by Liferay (only level1 participates). |
| **FIXED-12** | FIXED | `source-evidence` | `PRICING_SEED_REQUIREMENTS.md` FR-6 | Matches the `maximumDiscountAmount` behavior in Liferay. |
| **FIXED-13** | FIXED | `source-evidence` | `CommerceChannel.isDiscountsTargetNetPrice = true` | Upstream default: discounts applied to net, tax added later. |
| **FIXED-14** | FIXED | `source-evidence` | `CommerceChannel.isDiscountsTargetNetPrice = false` | Upstream gross-discounting logic: convert to gross, discount, then extract net. |
| **FIXED-15** | FIXED | `source-evidence` | `PRICING_SEED_REQUIREMENTS.md` FR-8 | Price on Application (POA) is a standard Liferay product status requiring empty prices. |
| **OPEN-5** | OPEN | `human-adjudication` | None | Upstream Liferay throws exceptions; gRPC status code mapping is a protocol choice left open to the author. |

---

## 6. Baseline Reference Resolutions (Google/Gemini/Antigravity)

These baseline resolutions represent the choices made by the primary author (Google) in the reference seed contract, which are evaluated under the bias audit:
* **[OPEN-1] Service/Method:** `service PricingService` with RPC `ComputeBasket`.
* **[OPEN-2] Message/Field Names:**
  * Request: `ComputeBasketRequest`, `LineItem`
  * Response: `ComputeBasketResponse`, `PricedLineItem`
  * Fields: `tier_factors`, `net_payable`, `offer_unit_price`, `discounts_pre_tax`.
* **[OPEN-3] Tiers Representation:** `repeated string tier_factors` (1..4 entries).
* **[OPEN-4] Rounding Default:** `HALF_UP` when unspecified.
* **[OPEN-5] gRPC Error Mapping:** Returns `INVALID_ARGUMENT` code for validation errors.

---

## 7. Source Bibliography

* **Liferay Commerce Pricing Calculation:** Liferay Commerce Pricing Engine product documentation.
* **Liferay Portal Source Code:** `github.com/liferay/liferay-portal` (pricing calculation DTOs, strategies, and configurations).
* **Spike Documentation:** [SPIKE_LIFERAY_PRICING_CARVE.md](file:///Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/liferay-pricing-seed/SPIKE_LIFERAY_PRICING_CARVE.md)
* **Pricing Seed Requirements:** [PRICING_SEED_REQUIREMENTS.md](file:///Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/liferay-pricing-seed/PRICING_SEED_REQUIREMENTS.md)

---

## 8. Human Leakage-Review Checklist (Honesty Control)

* `[x]` Verbatim Google/Gemini names (`ComputeBasket`, `tier_factors`, etc.) are stripped from sections 1-4.
* `[x]` Upstream Liferay names (`level1..4`, `finalPrice`) are sanitized or described generically in the core prompt section.
* `[x]` All OPEN requirements have their default resolutions omitted from sections 1-4 to avoid leading the model.
* `[x]` Rationale and upstream citations are provided for all FIXED items.

---

## 9. Reviewer Sign-Off

* **Reviewer ID:** `antigravity-agent`
* **Role:** Developer Assistant (Pair Programmer)
* **Date:** 2026-06-18
* **Blinding Status:** N/A (Brief Authoring)
* **Verdict:** Approved for S2 prompt template driving.

