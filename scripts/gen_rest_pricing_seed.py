#!/usr/bin/env python3
"""Generate the REST/HTTP hardened pricing seed (Track 2 REST lane — docs/design/benchmark-rest-lane/).

The HTTP counterpart to the gRPC pricing seed. Pins **python** with a stdlib `http.server` (zero
vendored deps — REST seeds skip proto provisioning entirely), declares `startup.readiness:"http"` +
`health_path`, and embeds the OpenAPI-derived REST contract + the same Liferay-derived pricing
semantics in `requirements_text`. Registered in the hardened-index under protocol "rest".
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/design/model-benchmark/seeds/seed-rest-pricingservice.json"
INDEX = ROOT / "docs/design/model-benchmark/seeds/hardened-index.json"

SPEC = """## Hardened benchmark — Pricing calculator (python, REST/HTTP)

Implement a **stateless REST pricing calculator** as an HTTP server in **python** using only the
**standard library** (`http.server`) — no third-party framework, no network. Every input is already
resolved (price-list selection, discount eligibility, coupon validation, address→tax-rate are upstream
and passed in). Target file: `src/rest_pricingservice/server.py`. Bind `0.0.0.0:$PORT` (the `PORT` env
var carries the port).

### Endpoints
- `GET /health` → `200` (any 2xx; body ignored) — readiness.
- `POST /price` → `200` with the priced basket JSON below, or `400` on invalid input.

### Request JSON (POST /price)
```json
{
  "items": [{
    "sku": "A", "quantity": "2", "unit_price": "10.00",
    "offer_unit_price": "",            // "" = none
    "price_on_application": false,
    "discounts": [{ "kind": "PERCENTAGE|FIXED_AMOUNT",
                    "tier_factors": ["10","10"],   // 1..4 entries
                    "maximum_amount": "" }],         // "" = uncapped
    "tax_rate": ""                     // percent, e.g. "20"; "" = 0
  }],
  "strategy": "CHAIN|ADDITION",
  "currency": { "code": "USD", "scale": 2, "rounding": "HALF_UP|HALF_EVEN" },
  "calculate_tax": false,
  "discounts_pre_tax": true
}
```

### Response JSON (200)
```json
{ "items": [{ "sku": "A", "unit_price": "10.00", "offer_unit_price": "",
              "net_payable": "20.00", "tax_value": "0.00", "net_payable_with_tax": "20.00",
              "discount_value": { "amount": "0.00", "percentage": "", "factor_percentages": [] },
              "price_on_application": false }],
  "subtotal_net_payable": "20.00", "subtotal_net_payable_with_tax": "20.00" }
```

### Money & rounding
- All amounts/quantities are decimal STRINGS; use EXACT decimal arithmetic (a float impl fails the
  rounding cases). Round monetary outputs to `currency.scale` using `currency.rounding`
  (HALF_UP | HALF_EVEN); emit each as a string at exactly `scale` digits.

### Per line item (price_on_application = false)
1. Base unit = `unit_price`, unless `offer_unit_price` is non-empty, > 0, and < `unit_price` (promo-min).
2. Line base = base unit × `quantity`.
3. Apply each discount in order to the running amount:
   - PERCENTAGE: `tier_factors` are percents combined by `strategy` — CHAIN: each tier on the running
     amount (`d ← d − d×tier/100`); ADDITION: `d ← d × (1 − Σtiers/100)`.
   - FIXED_AMOUNT: per-line absolute = `tier_factors[0]` (≤ running amount).
   - `maximum_amount` caps that discount's amount.
4. Tax (only if `calculate_tax`; `tax_rate` percent, "" = 0):
   - `discounts_pre_tax`=true: round NET → `net_payable`; `tax_value`=round(net×rate/100);
     `net_payable_with_tax`=net+tax.
   - `discounts_pre_tax`=false: GROSS = line×(1+rate/100), discount the gross → round to
     `net_payable_with_tax`; `net_payable`=round(with_tax/(1+rate/100)); `tax_value`=with_tax−net.
   - `calculate_tax`=false: `tax_value`="0.00"; `net_payable_with_tax`=`net_payable`.
5. Per-item output: `unit_price`, `offer_unit_price` (only when applied), `net_payable`, `tax_value`,
   `net_payable_with_tax`, `discount_value.amount` (= rounded base − discounted), `price_on_application`=false.

### price_on_application
If `price_on_application` is true, echo it true with all numeric price fields empty (""). Do not price it.

### Subtotals
`subtotal_net_payable` = Σ item `net_payable`; `subtotal_net_payable_with_tax` = Σ item `net_payable_with_tax`.

### Validation — respond HTTP 400 when:
- any `quantity` ≤ 0, or a malformed/negative price or quantity;
- any discount has 0 or more than 4 `tier_factors`;
- `strategy` is not "CHAIN" or "ADDITION" while any item carries a discount.
"""

TASK_DESCRIPTION = (
    "Implement a stateless REST pricing calculator as a stdlib-only python http.server. POST /price "
    "prices a basket of already-resolved line items (promo-min, 1..4-tier discounts combined by a "
    "CHAIN or ADDITION strategy, an optional per-discount cap, optional tax before or after discounts, "
    "exact decimal arithmetic with an explicit rounding mode, price-on-application pass-through, and "
    "input validation returning HTTP 400). GET /health returns 200. No third-party framework."
)


def main() -> None:
    spec_sha = hashlib.sha256(SPEC.encode()).hexdigest()
    rationale = (
        "Synthetic hardened REST seed. Pinned to python + stdlib http.server because the REST lane "
        "needs no vendored runtime (zero deps) and the harness's http readiness probe (FR-2/FR-11) "
        "drives any HTTP server; there is no canonical upstream language for a derived contract."
    )
    seed = {
        "generator": "scripts/gen_rest_pricing_seed.py",
        "schema_version": "1.0",
        "service_metadata": {
            "dependencies": [],
            "estimated_loc": 240,
            "language": "python",
            "language_rationale": rationale,
            "protocol": "rest",
            "endpoints": ["POST /price", "GET /health"],
            "spec_sha256": spec_sha,
            "service": "rest-pricingservice",
        },
        "startup": {
            "cmd": ["python3", "src/rest_pricingservice/server.py"],
            "port_env": "PORT",
            "readiness": "http",
            "health_path": "/health",
        },
        "tasks": [
            {
                "config": {
                    "context": {
                        "artifact_types_addressed": ["rest_service"],
                        "estimated_loc": 240,
                        "feature_id": "HARDENED-REST-PRICINGSERVICE",
                        "language": "python",
                        "protocol": "rest",
                        "target_files": ["src/rest_pricingservice/server.py"],
                    },
                    "requirements_text": SPEC,
                    "task_description": TASK_DESCRIPTION,
                },
                "depends_on": [],
                "task_id": "HARDENED-REST-PRICINGSERVICE",
                "task_type": "task",
                "title": "Pricing calculator (python, REST/HTTP) — hardened-tier",
            }
        ],
        "version": "0.1",
    }
    seed_bytes = json.dumps(seed, indent=2, sort_keys=True) + "\n"
    OUT.write_text(seed_bytes)
    seed_sha = hashlib.sha256(seed_bytes.encode()).hexdigest()
    print(f"wrote {OUT} (spec_sha256={spec_sha[:12]})")

    index = {"generator": "multiple", "schema_version": "1.0", "tier": "hardened", "seeds": []}
    if INDEX.exists():
        index = json.loads(INDEX.read_text())
    entry = {
        "service": "rest-pricingservice",
        "language": "python",
        "protocol": "rest",
        "seed_file": OUT.name,
        "seed_sha256": seed_sha,
        "target_file": "src/rest_pricingservice/server.py",
        "axes": ["B", "C", "E"],
        "derived_from": "Liferay Commerce headless-commerce pricing (REST) — docs/design/benchmark-rest-lane/",
    }
    others = [s for s in index.get("seeds", []) if s.get("service") != "rest-pricingservice"]
    index["seeds"] = sorted(others + [entry], key=lambda s: s["service"])
    INDEX.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    print(f"registered in {INDEX} (seed_sha256={seed_sha[:12]})")


if __name__ == "__main__":
    main()
