#!/usr/bin/env python3
"""Generate per-service Online Boutique benchmark seeds (M2 — FR-8/FR-31).

Emits one deterministic ``prime-context-seed.json`` per gRPC backend service under
``docs/design/model-benchmark/seeds/``, each carrying:
  - the task to implement that one service in its PINNED native language (FR-31),
  - the full demo.proto contract embedded in requirements_text (OQ-5: models get
    the contract; all OB services share one proto, so embedding it whole is faithful),
  - service_metadata (language + rationale + rpc/dependency info; FR-48 head start).

Deterministic + byte-stable (R1-S9): no timestamps in seed bodies, sorted keys, so
re-running yields identical files (and identical sha256). The seeds are the checked-in,
reproducible benchmark inputs (FR-19). Online Boutique is Apache-2.0; the vendored
demo.proto retains its license header (FR-49).

Usage:
    python3 scripts/gen_ob_benchmark_seeds.py            # write seeds + index
    python3 scripts/gen_ob_benchmark_seeds.py --check     # verify on-disk == generated (CI)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SEEDS_DIR = Path(__file__).resolve().parent.parent / "docs" / "design" / "model-benchmark" / "seeds"
PROTO_PATH = SEEDS_DIR / "demo.proto"
SCHEMA_VERSION = "1.0"
GENERATOR = "gen_ob_benchmark_seeds.py"

# The 9 gRPC backend services (frontend + loadgenerator are HTTP, macro-only).
# Native language is PINNED to canonical hipstershop (FR-31) with a one-line rationale.
SERVICES = [
    {
        "key": "cartservice", "proto_service": "CartService", "language": "csharp",
        "target_file": "src/cartservice/src/services/CartService.cs",
        "rpcs": ["AddItem", "GetCart", "EmptyCart"],
        "deps": ["Redis (cart storage)"],
        "estimated_loc": 180,
        "description": "Stores items in the user's shopping cart in Redis and retrieves them.",
        # Track 2 behavioral execution (FR-X6-CONTRACT / E6): launch the published .NET DLL offline.
        "startup": {
            "cmd": ["sh", "-c", "cd src/cartservice && exec dotnet ./.bin/server.dll"],
            "port_env": "PORT",
            "readiness": "tcp",
            "_note": "FR-X6-CONTRACT / E6: launches the published .NET service DLL (the _csharp_default ./.bin/server.dll convention — no `dotnet run`/restore under the sandbox). PORT injected via env; Kestrel-hosted variants also honor ASPNETCORE_URLS (set by the _csharp_default launcher). Serves CartService (AddItem/GetCart/EmptyCart). Cart state is Redis (FR-X3-STATE / FR-X5-DEPS — provisioned offline at prepare time; not a gRPC peer, so no dependency_addr_env). RESOLVABLE-BUT-PROVISIONING-DEFERRED: the startup contract resolves to a valid launch plan, but the offline .NET publish closure (./.bin/server.dll) + Redis provisioning are NOT yet built here — if absent the cell degrades at boot with the reason named (FR-X5-LANG), never false-0. TCP-listening readiness probe (gRPC).",
        },
    },
    {
        "key": "productcatalogservice", "proto_service": "ProductCatalogService", "language": "go",
        "target_file": "src/productcatalogservice/server.go",
        "rpcs": ["ListProducts", "GetProduct", "SearchProducts"],
        "deps": ["products.json (catalog data file)"],
        "estimated_loc": 220,
        "description": "Provides the product list from a JSON file plus search and single-product lookup.",
        # Track 2 behavioral execution (FR-X6-CONTRACT): launch the prebuilt Go binary offline.
        "startup": {
            "cmd": ["sh", "-c", "cd src/productcatalogservice && exec ./.bin/server"],
            "port_env": "PORT",
            "readiness": "tcp",
            "_note": "FR-X6-CONTRACT: launches the prebuilt Go binary (the _go_default ./.bin/server convention). Serves ProductCatalogService (ListProducts/GetProduct/SearchProducts). State is the local products.json catalog data file (FR-X5-DEPS provisioning, deferred) — no gRPC dependencies, so no dependency_addr_env. TCP-listening readiness probe (gRPC).",
        },
    },
    {
        "key": "currencyservice", "proto_service": "CurrencyService", "language": "nodejs",
        "target_file": "src/currencyservice/server.js",
        "rpcs": ["GetSupportedCurrencies", "Convert"],
        "deps": ["ECB currency rates (data file)"],
        "estimated_loc": 160,
        "description": "Converts money between currencies using ECB rates. Highest-QPS service.",
        # Hardened difficulty tier (FR-1/FR-10): stricter Money-type correctness within the SAME proto
        # (no new RPCs). Paired with the hardened currency suite's invariant probes (FR-12).
        "hardened": {
            "startup": {"cmd": ["node", "src/currencyservice/server.js"],
                        "port_env": "PORT", "readiness": "tcp"},
            "requirements_extra": (
                "## Hardened correctness requirements (tier: hardened)\n\n"
                "Implement `Convert` with full Money-type correctness — these are scored behaviorally:\n"
                "- **Single self-contained file:** put ALL logic in the one target `server.js` and INLINE "
                "the rate table. Do NOT `require` sibling modules you also write (e.g. `./loaders/...`) or "
                "read external data files (e.g. `data/*.json`) — the harness runs only this file offline. "
                "Do Money math with exact integer `units`/`nanos` arithmetic (no decimal/bignum library).\n"
                "- **Money contract:** `nanos` MUST be in [-999,999,999, +999,999,999], and the sign of "
                "`nanos` MUST match the sign of `units` (e.g. -$1.75 ⇒ units=-1, nanos=-750000000). "
                "Normalize any sub-unit remainder into `units`/`nanos`; never leave `nanos` out of range.\n"
                "- **Linear & lossless to nano precision:** converting 0 of any currency returns exactly 0; "
                "converting an amount and then converting the result back to the original currency MUST "
                "recover the original amount (within rounding to the nearest nano).\n"
                "- **Validation:** reject an unknown/unsupported ISO-4217 `to_code` (or unsupported source "
                "currency) with gRPC status `INVALID_ARGUMENT` — never return a zero or garbage amount.\n"
                "- `GetSupportedCurrencies` MUST return the exact set of codes that `Convert` accepts.\n"
                "- `Convert` MUST be deterministic for a given input.\n"
            ),
        },
    },
    {
        "key": "paymentservice", "proto_service": "PaymentService", "language": "nodejs",
        "target_file": "src/paymentservice/server.js",
        "rpcs": ["Charge"],
        "deps": [],
        "estimated_loc": 140,
        "description": "Charges the given (mock) credit card for an amount and returns a transaction ID.",
        # Track 2 behavioral execution (FR-T2-CONTRACT): fixed launch contract so every model
        # builds a launchable service. Harness injects PORT; readiness = TCP listen on 127.0.0.1.
        "startup": {
            "cmd": ["node", "src/paymentservice/server.js"],
            "port_env": "PORT",
            "readiness": "tcp",
        },
        # Hardened tier (FR-1/FR-10): stricter Charge validation + uniqueness, within the SAME proto.
        # Paired with charge_suite's hardened invariant probes (FR-12).
        "hardened": {
            "startup": {"cmd": ["node", "src/paymentservice/server.js"],
                        "port_env": "PORT", "readiness": "tcp"},
            "requirements_extra": (
                "## Hardened correctness requirements (tier: hardened)\n\n"
                "Implement `Charge` with strict validation — these are scored behaviorally:\n"
                "- **Single self-contained file:** put ALL logic in the one target `server.js`. Do NOT "
                "`require` sibling modules you also write (e.g. `./loaders/...`) or read external data "
                "files — the harness runs only this file with the offline gRPC runtime.\n"
                "- **Unique transaction id:** every successful `Charge` MUST return a UNIQUE non-empty "
                "`transaction_id` (e.g. a UUID) — never a constant.\n"
                "- **Amount validation:** reject a non-positive amount — BOTH negative `units` AND a "
                "zero amount (units==0 && nanos==0) — with gRPC `INVALID_ARGUMENT`.\n"
                "- **Card validation:** reject an empty/blank `credit_card_number`, a Luhn-invalid card, "
                "an expiry month outside 1–12, and an expired card — all with gRPC `INVALID_ARGUMENT`.\n"
            ),
        },
    },
    {
        "key": "shippingservice", "proto_service": "ShippingService", "language": "go",
        "target_file": "src/shippingservice/main.go",
        "rpcs": ["GetQuote", "ShipOrder"],
        "deps": [],
        "estimated_loc": 170,
        "description": "Gives shipping cost estimates for a cart and ships items to an address (mock).",
    },
    {
        "key": "emailservice", "proto_service": "EmailService", "language": "python",
        "target_file": "src/emailservice/email_server.py",
        "rpcs": ["SendOrderConfirmation"],
        "deps": ["Jinja2 HTML template"],
        "estimated_loc": 150,
        "description": "Sends an order-confirmation email (mock; logs in dummy mode) via a Jinja2 template.",
        # Track 2 behavioral execution (FR-X6-CONTRACT): launch the Python entry script offline.
        "startup": {
            "cmd": ["sh", "-c", "cd src/emailservice && exec python3 email_server.py"],
            "port_env": "PORT",
            "readiness": "tcp",
            "_note": "FR-X6-CONTRACT: launches the Python entry script directly (the _python_default convention), PORT injected via env (OB convention). Serves EmailService (SendOrderConfirmation). Leaf service — no gRPC dependencies, so no dependency_addr_env. Its only dependency is the local Jinja2 HTML template (FR-X5-DEPS templating-lib provisioning, deferred). TCP-listening readiness probe (gRPC).",
        },
    },
    {
        "key": "checkoutservice", "proto_service": "CheckoutService", "language": "go",
        "target_file": "src/checkoutservice/main.go",
        "rpcs": ["PlaceOrder"],
        "deps": ["productcatalogservice", "cartservice", "currencyservice",
                 "shippingservice", "paymentservice", "emailservice"],
        "estimated_loc": 320,
        "description": "Orchestration service: retrieves the cart, prepares the order, and coordinates "
                       "payment, shipping, and email. Highest-complexity service (6 gRPC dependencies).",
        # Track 2 behavioral execution (FR-CO-9/10): launch the prebuilt Go binary; the 6
        # *_SERVICE_ADDR env NAMES are declared here, the suite harness fills their VALUES at runtime.
        "startup": {
            "cmd": ["sh", "-c", "cd src/checkoutservice && exec ./.bin/server"],
            "port_env": "PORT",
            "readiness": "tcp",
            "dependency_addr_env": [
                "PRODUCT_CATALOG_SERVICE_ADDR",
                "CART_SERVICE_ADDR",
                "CURRENCY_SERVICE_ADDR",
                "SHIPPING_SERVICE_ADDR",
                "PAYMENT_SERVICE_ADDR",
                "EMAIL_SERVICE_ADDR",
            ],
            "_note": "FR-CO-9/10: launches the prebuilt Go binary (the _go_default ./.bin/server convention). 'dependency_addr_env' declares the six *_SERVICE_ADDR env NAMES only; the execute.py checkout branch binds the in-process stubs and fills these VALUES (127.0.0.1:<stubport>) into extra_env at suite runtime — never hardcoded here, since stub ports bind at run time.",
        },
    },
    {
        "key": "recommendationservice", "proto_service": "RecommendationService", "language": "python",
        "target_file": "src/recommendationservice/recommendation_server.py",
        "rpcs": ["ListRecommendations"],
        "deps": ["productcatalogservice"],
        "estimated_loc": 120,
        "description": "Recommends products based on the cart contents; calls ProductCatalogService.",
        # Track 2 behavioral execution (FR-X6-CONTRACT): launch the Python entry script; the
        # productcatalogservice address env NAME is declared here, the harness fills its VALUE at runtime.
        "startup": {
            "cmd": ["sh", "-c", "cd src/recommendationservice && exec python3 recommendation_server.py"],
            "port_env": "PORT",
            "readiness": "tcp",
            "dependency_addr_env": [
                "PRODUCT_CATALOG_SERVICE_ADDR",
            ],
            "_note": "FR-X6-CONTRACT: launches the Python entry script directly (the _python_default convention), PORT injected via env (OB convention). Serves RecommendationService (ListRecommendations). 'dependency_addr_env' declares the productcatalogservice address env NAME only; the suite harness binds a productcatalogservice stub and fills 127.0.0.1:<stubport> into extra_env at run time (FR-X5-DEPS dep stub, deferred — never hardcoded here). TCP-listening readiness probe (gRPC).",
        },
    },
    {
        "key": "adservice", "proto_service": "AdService", "language": "java",
        "target_file": "src/adservice/src/main/java/hipstershop/AdService.java",
        "rpcs": ["GetAds"],
        "deps": [],
        "estimated_loc": 200,
        "description": "Provides contextual text ads based on supplied context keywords.",
    },
]

LANGUAGE_RATIONALE = "Canonical native language of this service in GoogleCloudPlatform/microservices-demo (hipstershop), pinned constant across all models/reps for cross-language comparability (FR-31)."


def _task_description(svc: dict) -> str:
    return (
        f"Implement the **{svc['proto_service']}** gRPC service for the Online Boutique "
        f"microservices demo, in **{svc['language']}** (its canonical native language). "
        f"{svc['description']} Implement exactly the RPCs defined for {svc['proto_service']} "
        f"in the embedded demo.proto contract: {', '.join(svc['rpcs'])}. Wire up a gRPC server "
        f"that serves these RPCs. Do not implement any other service from the proto."
    )


def _requirements_text(svc: dict, proto_text: str) -> str:
    deps = ", ".join(svc["deps"]) if svc["deps"] else "none (leaf service)"
    return (
        f"## Online Boutique — {svc['proto_service']} ({svc['language']})\n\n"
        f"Implement ONLY `{svc['proto_service']}` from the shared gRPC contract below. "
        f"All Online Boutique services share this single `demo.proto` (package hipstershop).\n\n"
        f"- RPCs to implement: {', '.join(svc['rpcs'])}\n"
        f"- Downstream gRPC dependencies (for context; out of scope to implement here): {deps}\n"
        f"- Target file: `{svc['target_file']}`\n\n"
        f"### demo.proto (Apache-2.0, GoogleCloudPlatform/microservices-demo)\n\n"
        f"```proto\n{proto_text}\n```\n"
    )


def build_seed(svc: dict, proto_text: str, proto_sha: str) -> dict:
    task_id = f"OB-{svc['key'].upper()}"
    seed = {
        "version": "0.1",
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "service_metadata": {
            "service": svc["key"],
            "proto_service": svc["proto_service"],
            "language": svc["language"],
            "language_rationale": LANGUAGE_RATIONALE,
            "rpc_count": len(svc["rpcs"]),
            "rpcs": svc["rpcs"],
            "dependencies": svc["deps"],
            "estimated_loc": svc["estimated_loc"],
            "proto_sha256": proto_sha,
        },
        "tasks": [
            {
                "task_id": task_id,
                "title": f"{svc['proto_service']} ({svc['language']}) — Online Boutique gRPC service",
                "task_type": "task",
                "depends_on": [],  # scored independently in the service x model matrix (FR-9)
                "config": {
                    "task_description": _task_description(svc),
                    "requirements_text": _requirements_text(svc, proto_text),
                    "context": {
                        "feature_id": task_id,
                        "target_files": [svc["target_file"]],
                        "language": svc["language"],
                        "language_rationale": LANGUAGE_RATIONALE,
                        "estimated_loc": svc["estimated_loc"],
                        "proto_sha256": proto_sha,
                        "artifact_types_addressed": ["grpc_service"],
                    },
                },
            }
        ],
    }
    # Track 2 behavioral execution: services with a fixed launch contract carry it (FR-T2-CONTRACT).
    if svc.get("startup"):
        seed["startup"] = svc["startup"]
    return seed


def build_hardened_seed(svc: dict, proto_text: str, proto_sha: str) -> dict:
    """Hardened-tier seed = baseline seed + stricter requirements_text + an explicit startup contract
    (FR-1/FR-10). Additive; the SAME proto/RPCs — difficulty is correctness stringency, not surface."""
    h = svc["hardened"]
    seed = build_seed(svc, proto_text, proto_sha)
    seed["tier"] = "hardened"
    task = seed["tasks"][0]
    task["title"] += " [hardened]"
    task["config"]["requirements_text"] += "\n" + h["requirements_extra"]
    if h.get("startup"):
        seed["startup"] = h["startup"]
    return seed


def _serialize(seed: dict) -> str:
    # sorted keys + trailing newline → byte-stable across runs (R1-S9).
    return json.dumps(seed, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="Verify on-disk seeds match freshly-generated (no writes); exit 1 on drift.")
    args = ap.parse_args(argv)

    proto_text = PROTO_PATH.read_text(encoding="utf-8").rstrip("\n")
    proto_sha = hashlib.sha256((proto_text + "\n").encode("utf-8")).hexdigest()

    index = {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "proto": "demo.proto",
        "proto_sha256": proto_sha,
        "services": [],
        "hardened": [],  # additive difficulty-tier seeds (FR-1); baseline `services` unchanged
    }
    drift = False

    def _emit(seed: dict, out_name: str) -> str:
        """Serialize a seed, record/verify on disk, return its sha (shared baseline+hardened path)."""
        nonlocal drift
        text = _serialize(seed)
        out = SEEDS_DIR / out_name
        if args.check:
            current = out.read_text(encoding="utf-8") if out.exists() else None
            if current != text:
                print(f"DRIFT: {out_name}")
                drift = True
        else:
            out.write_text(text, encoding="utf-8")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    for svc in SERVICES:
        seed = build_seed(svc, proto_text, proto_sha)
        out_name = f"seed-{svc['key']}.json"
        seed_sha = _emit(seed, out_name)
        index["services"].append({
            "service": svc["key"], "language": svc["language"],
            "seed_file": out_name, "seed_sha256": seed_sha,
            "target_file": svc["target_file"],
        })
        # Additive hardened-tier seed (FR-1) for services that define a hardened overlay.
        if svc.get("hardened"):
            h_name = f"seed-{svc['key']}.hardened.json"
            h_sha = _emit(build_hardened_seed(svc, proto_text, proto_sha), h_name)
            index["hardened"].append({
                "service": svc["key"], "language": svc["language"], "tier": "hardened",
                "seed_file": h_name, "seed_sha256": h_sha, "target_file": svc["target_file"],
            })

    index_text = json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    index_path = SEEDS_DIR / "seeds-index.json"
    if args.check:
        if index_path.read_text(encoding="utf-8") != index_text if index_path.exists() else True:
            print("DRIFT: seeds-index.json")
            drift = True
        if drift:
            print("Seeds are OUT OF SYNC — run gen_ob_benchmark_seeds.py")
            return 1
        print(f"OK: {len(SERVICES)} seeds in sync")
        return 0

    index_path.write_text(index_text, encoding="utf-8")
    print(f"Wrote {len(SERVICES)} seeds + seeds-index.json to {SEEDS_DIR}")
    for s in index["services"]:
        print(f"  {s['service']:<26} {s['language']:<8} {s['seed_file']}  sha={s['seed_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
