#!/usr/bin/env python3
"""Generate the hardened-tier PricingService benchmark seed (docs/design/liferay-pricing-seed/).

Mirrors gen_ob_benchmark_seeds.py: emit a byte-stable seed JSON conforming to the benchmark seed
contract (service_metadata / startup / tasks+requirements_text), embedding pricing.proto + the
stringent ComputeBasket spec. The seed pins nodejs (FR-12) and declares the startup contract
(FR-10). Re-run after editing pricing.proto or the spec text.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTO = ROOT / "src/startd8/benchmark_matrix/behavioral/pricing.proto"
OUT = ROOT / "docs/design/model-benchmark/seeds/seed-pricingservice.json"
# Hardened-tier seeds get their OWN registry — NOT seeds-index.json, which is the Online Boutique
# baseline (single shared demo.proto, consumed by run_ob_benchmark.py). Keeps OB untouched (FR-14).
INDEX = ROOT / "docs/design/model-benchmark/seeds/hardened-index.json"

SPEC = """## Hardened benchmark — PricingService (nodejs)

Implement ONLY `PricingService.ComputeBasket` from the gRPC contract below. This is a **pure,
stateless price calculator**: every input is already resolved (price-list selection, discount
eligibility, coupon validation, and address→tax-rate resolution are performed upstream and passed
in). No database, no network, no global state.

- RPC to implement: ComputeBasket
- Target file: `src/pricingservice/server.js`
- The proto is provided as `pricing.proto` (and at conventional locations next to your server).

### Money & rounding
- All monetary amounts and quantities are decimal STRINGS (e.g. "29.97"). Use EXACT decimal
  arithmetic, NOT binary floating point — a float implementation will fail the rounding cases.
- `Currency.scale` is the number of fraction digits (e.g. 2). Round monetary OUTPUTS to `scale`
  using `Currency.rounding`: HALF_UP or HALF_EVEN. ROUNDING_MODE_UNSPECIFIED is treated as HALF_UP.
- Emit every monetary output as a string with exactly `scale` fraction digits (e.g. "20.00").

### Per line item (when price_on_application is false)
1. Base unit price = `unit_price`, UNLESS `offer_unit_price` is non-empty, > 0, and < `unit_price`,
   in which case the offer price replaces it (promo-min selection).
2. Line base = base unit price × `quantity` (exact).
3. Apply each discount in `discounts` order to the running amount:
   - PERCENTAGE: `tier_factors` are percents (1..4 of them). Combine them by `strategy`:
     - CHAIN: each tier applies to the running, already-discounted amount —
       d ← d − d × (tier / 100), for each tier in order.
     - ADDITION: sum the tiers and apply once — d ← d × (1 − (Σ tiers) / 100).
   - FIXED_AMOUNT: a per-line absolute discount = `tier_factors[0]` (any further tiers ignored);
     never more than the running amount.
   - If `maximum_amount` is set, cap that discount's amount at it.
4. Tax — only if `calculate_tax` is true; `tax_rate` is a percent ("" means 0:
   - `discounts_pre_tax` = true: round the discounted NET amount → `net_payable`; then
     `tax_value` = round(net_payable × rate / 100); `net_payable_with_tax` = net_payable + tax_value.
   - `discounts_pre_tax` = false: compute the GROSS base = line base × (1 + rate/100), apply the
     discounts to the gross, round it → `net_payable_with_tax`; then
     `net_payable` = round(net_payable_with_tax / (1 + rate/100)); `tax_value` =
     net_payable_with_tax − net_payable.
   - `calculate_tax` = false: `tax_value` = "0.00" (at scale); `net_payable_with_tax` = `net_payable`.
5. Per-item output: `unit_price`, `offer_unit_price` (only when the offer was applied),
   `net_payable`, `tax_value`, `net_payable_with_tax`, `discount_value.amount`
   (= rounded (discount base − discounted amount)), and `price_on_application` = false.

### price_on_application
If a line item has `price_on_application` = true, echo it back with `price_on_application` = true and
leave ALL numeric price fields empty (""). Do not compute a price for it.

### Subtotals
`subtotal_net_payable` = sum of each item's `net_payable`; `subtotal_net_payable_with_tax` = sum of
each item's `net_payable_with_tax` (both at currency scale).

### Validation — reject the whole request with gRPC status INVALID_ARGUMENT when:
- any `quantity` ≤ 0, or any malformed/negative price or quantity decimal;
- any discount has 0 tiers or more than 4 `tier_factors`;
- `strategy` = DISCOUNT_STRATEGY_UNSPECIFIED while any line item carries a discount.

### pricing.proto (DERIVED, not copied, from Liferay Commerce — package startd8.bench.pricing.v1)

```proto
{proto}
```
"""

TASK_DESCRIPTION = (
    "Implement the **PricingService** gRPC service as a pure, stateless price calculator in "
    "**nodejs**. ComputeBasket prices a basket of already-resolved line items: promo-min unit "
    "selection, 1..4-tier discounts combined by a CHAIN or ADDITION strategy, an optional "
    "per-discount cap, optional tax applied before or after discounts, exact decimal arithmetic "
    "with an explicit rounding mode, price-on-application pass-through, and input validation. "
    "Implement exactly the one RPC defined for PricingService in the embedded pricing.proto. Wire "
    "up a gRPC server that serves it. Do not implement anything else."
)


def main() -> None:
    proto_text = PROTO.read_text()
    proto_sha = hashlib.sha256(proto_text.encode()).hexdigest()
    requirements_text = SPEC.replace("{proto}", proto_text.rstrip())

    rationale = (
        "Synthetic hardened-tier seed (not an Online Boutique service). Pinned to nodejs because "
        "the Track 2 behavioral harness has a proven offline runtime closure for it (node_runtime/, "
        "dynamic @grpc/proto-loader); there is no canonical upstream language for a derived contract."
    )
    seed = {
        "generator": "scripts/gen_pricing_seed.py",
        "schema_version": "1.0",
        "service_metadata": {
            "dependencies": [],
            "estimated_loc": 220,
            "language": "nodejs",
            "language_rationale": rationale,
            "proto_service": "PricingService",
            "proto_sha256": proto_sha,
            "rpc_count": 1,
            "rpcs": ["ComputeBasket"],
            "service": "pricingservice",
        },
        "startup": {
            "cmd": ["node", "src/pricingservice/server.js"],
            "port_env": "PORT",
            "readiness": "tcp",
        },
        "tasks": [
            {
                "config": {
                    "context": {
                        "artifact_types_addressed": ["grpc_service"],
                        "estimated_loc": 220,
                        "feature_id": "HARDENED-PRICINGSERVICE",
                        "language": "nodejs",
                        "language_rationale": rationale,
                        "proto_sha256": proto_sha,
                        "target_files": ["src/pricingservice/server.js"],
                    },
                    "requirements_text": requirements_text,
                    "task_description": TASK_DESCRIPTION,
                },
                "depends_on": [],
                "task_id": "HARDENED-PRICINGSERVICE",
                "task_type": "task",
                "title": "PricingService (nodejs) — hardened-tier pricing calculator",
            }
        ],
        "version": "0.1",
    }
    seed_bytes = json.dumps(seed, indent=2, sort_keys=True) + "\n"
    OUT.write_text(seed_bytes)
    seed_sha = hashlib.sha256(seed_bytes.encode()).hexdigest()
    print(f"wrote {OUT} (proto_sha256={proto_sha})")

    # Upsert this seed's entry into the hardened-tier registry (per-seed proto, unlike the OB index).
    index = {"generator": "scripts/gen_pricing_seed.py", "schema_version": "1.0",
             "tier": "hardened", "seeds": []}
    if INDEX.exists():
        index = json.loads(INDEX.read_text())
    entry = {
        "service": "pricingservice",
        "language": "nodejs",
        "seed_file": OUT.name,
        "seed_sha256": seed_sha,
        "proto": "pricing.proto",
        "proto_sha256": proto_sha,
        "target_file": "src/pricingservice/server.js",
        "axes": ["B", "C", "E"],
        "derived_from": "Liferay Commerce (docs/design/liferay-pricing-seed/)",
    }
    others = [s for s in index.get("seeds", []) if s.get("service") != "pricingservice"]
    index["seeds"] = sorted(others + [entry], key=lambda s: s["service"])
    INDEX.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    print(f"registered in {INDEX} (seed_sha256={seed_sha[:12]})")


if __name__ == "__main__":
    main()
