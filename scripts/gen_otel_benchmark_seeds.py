#!/usr/bin/env python3
"""Generate per-service OpenTelemetry Demo benchmark seeds (Tier 1 — FR-1/FR-8).

Emits one deterministic ``prime-context-seed.json`` per covered gRPC service under
``docs/design/model-benchmark/seeds-otel/``, byte-schema-identical to the OB seeds so the
existing ``benchmark_matrix`` runner/scorer consumes them with zero code changes.

Consumes Tier-0 ``startup-capture.json`` when present (FR-2); each seed carries
``behavioral_eligible`` in ``service_metadata`` (FR-6).

Usage:
    python3 scripts/gen_otel_benchmark_seeds.py            # write seeds + index
    python3 scripts/gen_otel_benchmark_seeds.py --check   # verify on-disk == generated (CI)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS_DIR = REPO_ROOT / "docs" / "design" / "model-benchmark" / "seeds-otel"
PROTO_PATH = SEEDS_DIR / "demo.proto"
STARTUP_CAPTURE_PATH = REPO_ROOT / "docs" / "design" / "otel-demo-corpus" / "startup-capture.json"
SCHEMA_VERSION = "1.0"
GENERATOR = "gen_otel_benchmark_seeds.py"
CORPUS = "OpenTelemetry Demo (Astronomy Shop)"
CORPUS_REPO = "open-telemetry/opentelemetry-demo"
PROTO_PACKAGE = "oteldemo"

BEHAVIORAL_LANGUAGES = frozenset({"python", "go", "nodejs"})

# Runtime dependency markers — DB, broker, or downstream gRPC (not static data files).
_RUNTIME_MARKERS = (
    "postgresql",
    "postgres",
    "valkey",
    "redis",
    "kafka",
    "broker",
    "database",
    "llm",
)
_DOWNSTREAM_GRPC = (
    "product-catalog",
    "cart",
    "currency",
    "shipping",
    "email",
    "payment",
    "checkout",
    "recommendation",
)

# Seven covered gRPC services (OTEL_DEMO_SEED_EXTRACTION_PLAN.md §2).
SERVICES = [
    {
        "key": "checkout",
        "proto_service": "CheckoutService",
        "language": "go",
        "target_file": "src/checkout/main.go",
        "rpcs": ["PlaceOrder"],
        "deps": [
            "product-catalog",
            "cart",
            "currency",
            "shipping",
            "email",
            "payment",
            "Kafka (order events)",
        ],
        "estimated_loc": 380,
        "description": (
            "Orchestration service: coordinates cart, catalog, currency, shipping, email, "
            "and payment for PlaceOrder; publishes order events to Kafka."
        ),
    },
    {
        "key": "product-catalog",
        "proto_service": "ProductCatalogService",
        "language": "go",
        "target_file": "src/product-catalog/main.go",
        "rpcs": ["ListProducts", "GetProduct", "SearchProducts"],
        "deps": ["products.json (catalog data file)"],
        "estimated_loc": 220,
        "description": "Provides the product list from a JSON file plus search and single-product lookup.",
    },
    {
        "key": "recommendation",
        "proto_service": "RecommendationService",
        "language": "python",
        "target_file": "src/recommendation/recommendation_server.py",
        "rpcs": ["ListRecommendations"],
        "deps": ["product-catalog"],
        "estimated_loc": 130,
        "description": "Recommends products based on cart contents; calls ProductCatalogService.",
    },
    {
        "key": "product-reviews",
        "proto_service": "ProductReviewService",
        "language": "python",
        "target_file": "src/product-reviews/product_reviews_server.py",
        "rpcs": ["GetProductReviews", "GetAverageProductReviewScore"],
        "deps": ["PostgreSQL (declared; not required at generation)"],
        "estimated_loc": 200,
        "description": (
            "Returns product reviews and average scores from Postgres. "
            "Omit AskProductAIAssistant (LLM dependency)."
        ),
    },
    {
        "key": "cart",
        "proto_service": "CartService",
        "language": "csharp",
        "target_file": "src/cart/src/services/CartService.cs",
        "rpcs": ["AddItem", "GetCart", "EmptyCart"],
        "deps": ["Valkey (cart storage)"],
        "estimated_loc": 190,
        "description": "Stores items in the user's shopping cart in Valkey/Redis and retrieves them.",
    },
    {
        "key": "ad",
        "proto_service": "AdService",
        "language": "java",
        "target_file": "src/ad/src/main/java/oteldemo/AdService.java",
        "rpcs": ["GetAds"],
        "deps": [],
        "estimated_loc": 200,
        "description": "Provides contextual text ads based on supplied context keywords.",
    },
    {
        "key": "payment",
        "proto_service": "PaymentService",
        "language": "nodejs",
        "target_file": "src/payment/charge.js",
        "rpcs": ["Charge"],
        "deps": [],
        "estimated_loc": 140,
        "description": "Charges the given (mock) credit card for an amount and returns a transaction ID.",
    },
]

LANGUAGE_RATIONALE = (
    f"Canonical native language of this service in {CORPUS_REPO} ({PROTO_PACKAGE}), "
    "pinned constant across all models/reps for cross-language comparability (FR-31)."
)


def _has_runtime_dep(deps: list[str]) -> bool:
    for dep in deps:
        low = dep.lower().strip()
        if any(m in low for m in _RUNTIME_MARKERS):
            return True
        if ".json" in low or "data file" in low:
            continue
        # Downstream gRPC: match the service token exactly (avoid "cart" ⊂ "product-catalog").
        head = re.split(r"[\s(,]+", low.replace("_", "-"), maxsplit=1)[0]
        if head in _DOWNSTREAM_GRPC:
            return True
    return False


def behavioral_eligible(svc: dict) -> bool:
    """True iff securely-provisioned language AND no required-at-runtime external dep (FR-6)."""
    return svc["language"] in BEHAVIORAL_LANGUAGES and not _has_runtime_dep(svc["deps"])


def _task_id(svc: dict) -> str:
    return f"OTEL-{svc['key'].upper().replace('-', '_')}"


def _task_description(svc: dict) -> str:
    return (
        f"Implement the **{svc['proto_service']}** gRPC service for the {CORPUS} "
        f"microservices demo, in **{svc['language']}** (its canonical native language). "
        f"{svc['description']} Implement exactly the RPCs defined for {svc['proto_service']} "
        f"in the embedded demo.proto contract: {', '.join(svc['rpcs'])}. Wire up a gRPC server "
        f"that serves these RPCs. Do not implement any other service from the proto."
    )


def _requirements_text(svc: dict, proto_text: str) -> str:
    deps = ", ".join(svc["deps"]) if svc["deps"] else "none (leaf service)"
    return (
        f"## {CORPUS} — {svc['proto_service']} ({svc['language']})\n\n"
        f"Implement ONLY `{svc['proto_service']}` from the shared gRPC contract below. "
        f"All {CORPUS} services share this single `demo.proto` (package {PROTO_PACKAGE}).\n\n"
        f"- RPCs to implement: {', '.join(svc['rpcs'])}\n"
        f"- Downstream gRPC dependencies (for context; out of scope to implement here): {deps}\n"
        f"- Target file: `{svc['target_file']}`\n\n"
        f"### demo.proto (Apache-2.0, {CORPUS_REPO})\n\n"
        f"```proto\n{proto_text}\n```\n"
    )


def load_startup_capture(path: Path = STARTUP_CAPTURE_PATH) -> dict[str, dict]:
    """Map compose_service -> startup block from Tier-0 FR-7 capture."""
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for row in doc.get("services") or []:
        compose = row.get("compose_service")
        startup = row.get("startup") or {}
        if not compose or not startup.get("cmd"):
            continue
        block = {k: startup[k] for k in ("cmd", "port_env", "readiness") if k in startup}
        if block.get("cmd"):
            out[compose] = block
    return out


def build_seed(
    svc: dict,
    proto_text: str,
    proto_sha: str,
    *,
    startup_capture: dict[str, dict],
) -> dict:
    eligible = behavioral_eligible(svc)
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
            "corpus": "otel-demo",
            "behavioral_eligible": eligible,
        },
        "tasks": [
            {
                "task_id": _task_id(svc),
                "title": f"{svc['proto_service']} ({svc['language']}) — {CORPUS} gRPC service",
                "task_type": "task",
                "depends_on": [],
                "config": {
                    "task_description": _task_description(svc),
                    "requirements_text": _requirements_text(svc, proto_text),
                    "context": {
                        "feature_id": _task_id(svc),
                        "target_files": [svc["target_file"]],
                        "language": svc["language"],
                        "language_rationale": LANGUAGE_RATIONALE,
                        "estimated_loc": svc["estimated_loc"],
                        "proto_sha256": proto_sha,
                        "artifact_types_addressed": ["grpc_service"],
                        "corpus": "otel-demo",
                        "behavioral_eligible": eligible,
                    },
                },
            }
        ],
    }
    startup = startup_capture.get(svc["key"])
    if startup:
        seed["startup"] = startup
    return seed


def _serialize(seed: dict) -> str:
    return json.dumps(seed, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="Verify on-disk seeds match freshly-generated (no writes); exit 1 on drift.",
    )
    ap.add_argument(
        "--startup-capture",
        type=Path,
        default=None,
        help="Tier-0 startup-capture.json (optional; FR-2). Ignored by --check unless explicitly set.",
    )
    args = ap.parse_args(argv)

    if not PROTO_PATH.is_file():
        print(f"ERROR: vendored proto missing: {PROTO_PATH}", file=sys.stderr)
        return 2

    proto_text = PROTO_PATH.read_text(encoding="utf-8").rstrip("\n")
    proto_sha = hashlib.sha256((proto_text + "\n").encode("utf-8")).hexdigest()
    expected_sha = "712594c1e1a144c2211ff0695d8db05864b4ddccfad2e9862cadff8ce311225f"
    if proto_sha != expected_sha:
        print(f"ERROR: demo.proto sha mismatch: got {proto_sha}, expected {expected_sha}", file=sys.stderr)
        return 2

    if args.check:
        # Committed seeds are byte-stable without local startup-capture (gitignored per-run artifact).
        startup_capture = (
            load_startup_capture(args.startup_capture)
            if args.startup_capture is not None
            else {}
        )
    else:
        capture_path = args.startup_capture or STARTUP_CAPTURE_PATH
        startup_capture = load_startup_capture(capture_path)
        if not startup_capture:
            print(
                f"NOTE: no startup capture at {capture_path} — seeds ship without startup blocks (FR-2).",
                file=sys.stderr,
            )

    index = {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "corpus": "otel-demo",
        "proto": "demo.proto",
        "proto_sha256": proto_sha,
        "services": [],
    }
    drift = False

    def _emit(seed: dict, out_name: str) -> str:
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
        seed = build_seed(svc, proto_text, proto_sha, startup_capture=startup_capture)
        out_name = f"seed-{svc['key']}.json"
        seed_sha = _emit(seed, out_name)
        index["services"].append(
            {
                "service": svc["key"],
                "language": svc["language"],
                "seed_file": out_name,
                "seed_sha256": seed_sha,
                "target_file": svc["target_file"],
                "behavioral_eligible": seed["service_metadata"]["behavioral_eligible"],
            }
        )

    index_text = json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    index_path = SEEDS_DIR / "seeds-index.json"
    if args.check:
        if index_path.read_text(encoding="utf-8") != index_text if index_path.is_file() else True:
            print("DRIFT: seeds-index.json")
            drift = True
        if drift:
            print("Seeds are OUT OF SYNC — run gen_otel_benchmark_seeds.py")
            return 1
        print(f"OK: {len(SERVICES)} OTel seeds in sync")
        return 0

    index_path.write_text(index_text, encoding="utf-8")
    print(f"Wrote {len(SERVICES)} seeds + seeds-index.json to {SEEDS_DIR}")
    for s in index["services"]:
        beh = "behavioral" if s["behavioral_eligible"] else "structural"
        print(f"  {s['service']:<18} {s['language']:<8} {beh:<11} {s['seed_file']}  sha={s['seed_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
