#!/usr/bin/env python3
"""Generate the GraphQL hardened pricing seed (Track 2 GraphQL lane — docs/design/benchmark-graphql-lane/).

The GraphQL counterpart to the gRPC + REST pricing seeds — the **hybrid** (FR-6): a `basket(input)`
operation (pure-calculator carve) returning a computed-field graph (GraphQL idiom), with GraphQL
selection sets exploited for memorization resistance (FR-10). Pins python; the model declares
`graphql-core` in requirements.txt (provisioned via the existing path). `startup.readiness:"http"`.
The canonical SDL is imported from the suite (single source of truth) and embedded in requirements_text.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from startd8.benchmark_matrix.behavioral.graphql_pricing_suite import SCHEMA_SDL  # noqa: E402

OUT = ROOT / "docs/design/model-benchmark/seeds/seed-graphql-pricingservice.json"
INDEX = ROOT / "docs/design/model-benchmark/seeds/hardened-index.json"

SPEC = """## Hardened benchmark — Pricing calculator (python, GraphQL)

Implement a **GraphQL** pricing calculator server in **python** (e.g. with `graphql-core`; declare it in
`requirements.txt`). Serve `POST /graphql` accepting `{{"query","variables"}}` and `GET /health` → 200.
Bind `0.0.0.0:$PORT`. Stateless: every input is explicit (resolution performed upstream).

### Schema (SDL — implement exactly)
```graphql
{sdl}
```

### GraphQL conventions (CRITICAL — different from REST)
- **Always respond HTTP 200.** Validation/computation errors go in the response body's top-level `errors`
  array (GraphQL spec), NEVER as a 4xx HTTP status.
- **Partial results:** a single invalid line errors ONLY that line (the `PricedLine` list element is
  nullable) — valid lines still resolve under `data`, and `errors[].path` points at the failing line,
  e.g. `["basket","lines",1,"netPayable"]`. Do not null-propagate the whole response.
- **Selection-driven:** return only the fields the client selected (standard GraphQL).

### Money & rounding
All amounts/quantities are decimal STRINGS; use EXACT decimal arithmetic (NOT float — it fails the
rounding cases). Round monetary outputs to `currency.scale` using `currency.rounding`
(HALF_UP | HALF_EVEN); emit each as a string at exactly `scale` digits.

### Pricing algorithm (per line, priceOnApplication = false)
1. Base unit = `unitPrice`, unless `offerUnitPrice` is non-null, > 0, and < `unitPrice` (promo-min).
2. Line base = base unit × `quantity`.
3. Apply each adjustment in order to the running amount:
   - PERCENTAGE: `tierFactors` are percents combined by `strategy` — CHAIN: each tier on the running
     amount (`d ← d − d×tier/100`); ADDITION: `d ← d × (1 − Σtiers/100)`.
   - FIXED_AMOUNT: per-line absolute = `tierFactors[0]` (≤ running amount).
   - `maximumAmount` caps that adjustment's amount.
4. Tax (only if `calculateTax`; `taxRate` percent, null = 0):
   - `adjustmentsPreTax`=true: round NET → `netPayable`; `taxValue`=round(net×rate/100);
     `netPayableWithTax`=net+tax.
   - `adjustmentsPreTax`=false: GROSS = line×(1+rate/100), adjust the gross → round to
     `netPayableWithTax`; `netPayable`=round(withTax/(1+rate/100)); `taxValue`=withTax−net.
   - `calculateTax`=false: `taxValue`="0.00"; `netPayableWithTax`=`netPayable`.

### AdjustmentBreakdown (the derivation fields — exposed AS data)
- `amount`: rounded total adjustment = round(base − discounted).
- `effectivePercent`: the COMBINED effective adjustment percent = round((lineBase − discounted)/lineBase
  × 100); "0.00" if no adjustments. NB this discriminates the strategy: tiers `[10,10]` → CHAIN "19.00",
  ADDITION "20.00".
- `tierPercents`: for PERCENTAGE adjustments, the input `tierFactors` concatenated; for FIXED_AMOUNT, a
  single-element list `[effectivePercent]`; empty list if no adjustments.

### Subtotals
`subtotalNetPayable` = Σ line `netPayable`; `subtotalNetPayableWithTax` = Σ line `netPayableWithTax`
(POA lines contribute 0). At currency scale.

### price_on_application
If a line's `priceOnApplication` is true, resolve `priceOnApplication=true` and the numeric string fields
("netPayable", etc.) as "".

### Validation
- **Basket-level** (whole operation errors, `data` null): `strategy` is not "CHAIN" or "ADDITION" while
  any line carries adjustments.
- **Line-level** (partial — error `path` at that line): negative/malformed quantity, negative/malformed
  price, or an adjustment with 0 or > 4 `tierFactors`.

(Note: this is a synthetic basket operation. Liferay surfaces pricing as a `Price` field on a SKU/product
and uses `Double`; the basket op + decimal-strings here are deliberate divergences — see the design docs.)
"""

TASK_DESCRIPTION = (
    "Implement a stateless GraphQL pricing calculator in python (graphql-core). The single `basket(input)` "
    "query prices a basket of already-resolved line items and returns a computed-field graph (per-line "
    "net/tax + an AdjustmentBreakdown derivation sub-graph + subtotals). Honor GraphQL conventions: HTTP "
    "200 always, errors in the body's `errors` array, partial results with correct `path` for an invalid "
    "line, and selection-driven responses. Serve POST /graphql and GET /health (200). Same pricing "
    "semantics as the gRPC/REST seeds (promo-min, chain/addition tiers, cap, tax pre/post, exact-decimal "
    "rounding, POA, validation)."
)


def main() -> None:
    sdl = SCHEMA_SDL.strip()
    requirements_text = SPEC.replace("{sdl}", sdl)
    spec_sha = hashlib.sha256(requirements_text.encode()).hexdigest()
    rationale = ("Synthetic hardened GraphQL seed. Pinned to python; the model declares graphql-core in "
                 "requirements.txt (provisioned via the existing path). Readiness is http-liveness.")
    seed = {
        "generator": "scripts/gen_graphql_pricing_seed.py",
        "schema_version": "1.0",
        "service_metadata": {
            "dependencies": ["graphql-core"],
            "estimated_loc": 320,
            "language": "python",
            "language_rationale": rationale,
            "protocol": "graphql",
            "endpoints": ["POST /graphql", "GET /health"],
            "spec_sha256": spec_sha,
            "service": "graphql-pricingservice",
        },
        "startup": {
            "cmd": ["python3", "src/graphql_pricingservice/server.py"],
            "port_env": "PORT",
            "readiness": "http",
            "health_path": "/health",
        },
        "tasks": [
            {
                "config": {
                    "context": {
                        "artifact_types_addressed": ["graphql_service"],
                        "estimated_loc": 320,
                        "feature_id": "HARDENED-GRAPHQL-PRICINGSERVICE",
                        "language": "python",
                        "protocol": "graphql",
                        "target_files": ["src/graphql_pricingservice/server.py"],
                    },
                    "requirements_text": requirements_text,
                    "task_description": TASK_DESCRIPTION,
                },
                "depends_on": [],
                "task_id": "HARDENED-GRAPHQL-PRICINGSERVICE",
                "task_type": "task",
                "title": "Pricing calculator (python, GraphQL) — hardened-tier",
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
        "service": "graphql-pricingservice",
        "language": "python",
        "protocol": "graphql",
        "seed_file": OUT.name,
        "seed_sha256": seed_sha,
        "target_file": "src/graphql_pricingservice/server.py",
        "axes": ["B", "C", "E"],
        "derived_from": "Liferay Commerce headless-commerce pricing (GraphQL) — docs/design/benchmark-graphql-lane/",
    }
    others = [s for s in index.get("seeds", []) if s.get("service") != "graphql-pricingservice"]
    index["seeds"] = sorted(others + [entry], key=lambda s: s["service"])
    INDEX.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    print(f"registered in {INDEX} (seed_sha256={seed_sha[:12]})")


if __name__ == "__main__":
    main()
