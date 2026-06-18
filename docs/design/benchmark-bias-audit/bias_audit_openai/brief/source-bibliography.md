# Source Bibliography

**Liferay repository:** `https://github.com/liferay/liferay-portal`  
**Commit inspected:** `4d9e440ee64aa31d2d60e525e20fa9837a4f4df7`  

## Upstream Liferay Files

- `modules/apps/commerce/commerce-api/src/main/java/com/liferay/commerce/price/CommerceProductPrice.java`
  - Key lines inspected: 20-46.
  - Supports result concepts: discount values, final price, final price with tax, quantity, tax value,
    unit price, unit price with tax, promo price, promo price with tax, POA.
- `modules/apps/commerce/commerce-api/src/main/java/com/liferay/commerce/price/CommerceProductPriceImpl.java`
  - Supports storage/mutation of the same result concepts.
- `modules/apps/commerce/commerce-api/src/main/java/com/liferay/commerce/discount/CommerceDiscountValue.java`
  - Key lines inspected: 18-41.
  - Supports discount amount, aggregate percentage, and percentage array.
- `modules/apps/commerce/commerce-pricing-api/src/main/java/com/liferay/commerce/pricing/configuration/CommercePricingConfiguration.java`
  - Key lines inspected: 26-30 and 46-55.
  - Supports configurable discount application strategy, price-list discovery, and promotion discovery.
- `modules/apps/commerce/commerce-discount-service/src/main/java/com/liferay/commerce/discount/internal/application/strategy/ChainCommerceDiscountApplicationStrategyImpl.java`
  - Key lines inspected: 24-46.
  - Supports chain discount behavior.
- `modules/apps/commerce/commerce-discount-service/src/main/java/com/liferay/commerce/discount/internal/application/strategy/AdditionCommerceDiscountApplicationStrategyImpl.java`
  - Key lines inspected: 24-49.
  - Supports addition discount behavior.
- `modules/apps/commerce/commerce-discount-service/src/main/java/com/liferay/commerce/discount/internal/CommerceDiscountCalculationV2Impl.java`
  - Key lines inspected: 193-229, 280-325, 333-380, 384-427, and 429-477.
  - Supports four levels, discount value generation, percentage discount maximum amount caps,
    fixed-amount discount price caps, currency rounding mode use, and scale 10 intermediate rounding.
- `modules/apps/commerce/commerce-service/src/main/java/com/liferay/commerce/internal/price/CommerceProductPriceCalculationV2Impl.java`
  - Key lines inspected: 143-168, 184-243, 260-328, 333-343, and 1480-1483.
  - Supports promo-price selection, POA interaction evidence, calculate-tax branching,
    net-versus-gross discount targeting, tax mirror population trigger, and channel tax-included display
    mode.
- `modules/apps/commerce/commerce-service/src/main/java/com/liferay/commerce/internal/price/BaseCommerceProductPriceCalculation.java`
  - Key lines inspected: 159-218 and 363-433.
  - Supports tax conversion dependency on contextual billing/shipping/channel/currency inputs and
    population of unit/final/discount tax-inclusive mirrors.
- `modules/apps/commerce/commerce-service/src/main/java/com/liferay/commerce/internal/price/BaseCommerceOrderPriceCalculation.java`
  - Key lines inspected: 60-190, 221-307, 375-455, and 505-610.
  - Supports order-level tax/with-tax output concepts, net-versus-gross discount conversion,
    tax-included display selection, promo price active-price selection rule, and currency rounding mode
    use in per-unit math.
- `modules/apps/commerce/commerce-service/src/main/java/com/liferay/commerce/internal/util/CommercePriceConverterUtil.java`
  - Key lines inspected: 27-94 and 115-145.
  - Supports converted discount values, tax-value aggregation, include-tax add/subtract behavior,
    percentage conversion, and scale 10 percentage-ratio rounding.
- `modules/apps/commerce/commerce-pricing-api/src/main/java/com/liferay/commerce/pricing/constants/CommercePricingConstants.java`
  - Key lines inspected: 31-39.
  - Supports tax-excluded and tax-included display constants.
- `modules/apps/commerce/headless/headless-commerce/headless-commerce-delivery-catalog-api/src/main/java/com/liferay/headless/commerce/delivery/catalog/dto/v1_0/Price.java`
  - Key lines inspected: 35-38, 101-149, 200-243, and 377-390.
  - Supports delivery DTO price snapshot, discount, discount percentages, final price, promo price,
    and POA concepts.

## Benchmark Schema Files

- [src/startd8/seeds/models.py](/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/seeds/models.py)
  - `ContextSeed` envelope and `SeedTask.from_seed_entry()` parser.
- [docs/design/model-benchmark/seeds/seed-paymentservice.json](/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/model-benchmark/seeds/seed-paymentservice.json)
  - Existing benchmark seed shape: generator, schema version, service metadata, startup, tasks,
    `requirements_text`, and target files.
- [src/startd8/benchmark_matrix/run_spec.py](/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/benchmark_matrix/run_spec.py)
  - Benchmark cell/service/repetition structure.

## Non-Authoritative Prior Art

These files were read to avoid copying existing semantic resolutions. They are not source authority for
FIXED/OPEN decisions in the neutral brief.

- [docs/design/liferay-pricing-seed/SPIKE_LIFERAY_PRICING_CARVE.md](/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/liferay-pricing-seed/SPIKE_LIFERAY_PRICING_CARVE.md)
- [docs/design/liferay-pricing-seed/PRICING_SEED_REQUIREMENTS.md](/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/liferay-pricing-seed/PRICING_SEED_REQUIREMENTS.md)
- [docs/design/liferay-pricing-seed/PRICING_SEED_PLAN.md](/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/liferay-pricing-seed/PRICING_SEED_PLAN.md)
- [scripts/gen_pricing_seed.py](/Users/neilyashinsky/Documents/dev/startd8-sdk/scripts/gen_pricing_seed.py)
- [src/startd8/benchmark_matrix/behavioral/pricing.proto](/Users/neilyashinsky/Documents/dev/startd8-sdk/src/startd8/benchmark_matrix/behavioral/pricing.proto)
