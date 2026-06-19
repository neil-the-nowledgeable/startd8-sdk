#!/usr/bin/env python3
"""Generate the canonical ResolvedPriceService benchmark seed envelope.

The seed is built from the OpenAI/Codex bias-audit canonical artifacts:
the frozen proto, prose spec, and suite manifest. It also upserts the seed
into hardened-index.json after the live resolvedpriceservice adapter exists.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "docs/design/benchmark-bias-audit/bias_audit_openai"
CANONICAL_DIR = AUDIT_DIR / "canonical"
SUITE_RUN_DIR = AUDIT_DIR / "runs/s2-codex-suite-clean-20260618T215301Z"
OUT = ROOT / "docs/design/model-benchmark/seeds/seed-resolvedpriceservice.json"
INDEX = ROOT / "docs/design/model-benchmark/seeds/hardened-index.json"

PROTO = CANONICAL_DIR / "pricing.proto"
SPEC = CANONICAL_DIR / "spec.md"
DECISIONS = CANONICAL_DIR / "canonicalization_decisions.md"
SUITE = SUITE_RUN_DIR / "suite.py"
SUITE_MANIFEST = SUITE_RUN_DIR / "suite_manifest.json"
SUITE_SCHEMA = SUITE_RUN_DIR / "self-manifest.schema.json"
SOURCE_BRIEF = AUDIT_DIR / "brief/pricing-task-brief.md"
TRACEABILITY = AUDIT_DIR / "brief/source-to-brief-traceability.md"
TRACEABILITY_CSV = AUDIT_DIR / "brief/source-to-brief-traceability.csv"

RUNTIME_DEPENDENCIES = [
    "@grpc/grpc-js@^1.10.0",
    "@grpc/proto-loader@^0.7.10",
    "decimal.js@^10.4.0",
]

LANGUAGE_RATIONALE = (
    "Pinned to nodejs because the benchmark Track 2 behavioral harness has a vendored offline "
    "Node runtime closure for grpc-js, proto-loader, and decimal.js. Liferay Java source evidence "
    "constrains the pricing semantics, not the benchmark runtime."
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_text(_read(path))


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _suite_counts(manifest: dict[str, Any]) -> dict[str, int]:
    names = list(manifest.get("test_case_names", []))
    invalid = sum(1 for name in names if str(name).startswith("rejects_"))
    return {
        "test_case_count": len(names),
        "valid_case_count": len(names) - invalid,
        "invalid_case_count": invalid,
    }


def _requirements_text(proto: str, spec: str) -> str:
    return (
        "## ResolvedPriceService (nodejs) -- Liferay-derived resolved-line pricing calculator\n\n"
        "Implement ONLY `ResolvedPriceService.AssessLines` from the gRPC contract below. This is a "
        "pure, stateless calculator for already-resolved line items: upstream systems have already "
        "selected price lists, determined discount eligibility, and decided whether a line is "
        "price-on-request. The service must not use a database, network call, clock, hidden state, "
        "or any external pricing source.\n\n"
        "- RPC to implement: `ResolvedPriceService.AssessLines`\n"
        "- Proto package: `benchmark.pricing.v1`\n"
        "- Target file: `src/resolvedpriceservice/server.js`\n"
        "- Runtime: Node.js gRPC server listening on `PORT`\n"
        "- The proto is provided as `pricing.proto` and may be loaded dynamically with "
        "`@grpc/proto-loader`.\n"
        "- Use exact decimal arithmetic for all parsing, comparison, arithmetic, and formatting. "
        "Do not use binary floating point for monetary values, quantities, or percentages.\n"
        "- Implement the canonical specification below exactly; do not add tax behavior, discount "
        "caps, persistence, lookup, or service-to-service calls.\n"
        "- Invalid requests fail the RPC with gRPC `INVALID_ARGUMENT`; tests do not require exact "
        "error-message wording.\n\n"
        "### Canonical pricing.proto\n\n"
        "```proto\n"
        f"{proto.rstrip()}\n"
        "```\n\n"
        "### Canonical functional specification\n\n"
        f"{spec.rstrip()}\n"
    )


def build_seed() -> dict[str, Any]:
    proto_text = _read(PROTO)
    spec_text = _read(SPEC)
    suite_manifest = json.loads(_read(SUITE_MANIFEST))
    suite_counts = _suite_counts(suite_manifest)

    proto_sha = _sha256_text(proto_text)
    spec_sha = _sha256_text(spec_text)
    suite_sha = _sha256_path(SUITE)
    suite_manifest_sha = _sha256_path(SUITE_MANIFEST)

    requirements_text = _requirements_text(proto_text, spec_text)

    artifacts = {
        "canonical_proto": {
            "path": _rel(PROTO),
            "role": "model_facing_contract",
            "sha256": proto_sha,
        },
        "canonical_spec": {
            "path": _rel(SPEC),
            "role": "model_facing_spec",
            "sha256": spec_sha,
        },
        "canonicalization_decisions": {
            "path": _rel(DECISIONS),
            "role": "audit_trace",
            "sha256": _sha256_path(DECISIONS),
        },
        "behavioral_suite": {
            "path": _rel(SUITE),
            "role": "validation_oracle_not_model_facing",
            "sha256": suite_sha,
            "suite_id": suite_manifest.get("suite_id", ""),
            **suite_counts,
        },
        "behavioral_suite_manifest": {
            "path": _rel(SUITE_MANIFEST),
            "role": "suite_trace",
            "sha256": suite_manifest_sha,
        },
        "behavioral_suite_schema": {
            "path": _rel(SUITE_SCHEMA),
            "role": "suite_manifest_schema",
            "sha256": _sha256_path(SUITE_SCHEMA),
        },
        "source_brief": {
            "path": _rel(SOURCE_BRIEF),
            "role": "upstream_liferay_evidence_brief",
            "sha256": _sha256_path(SOURCE_BRIEF),
        },
        "source_traceability_matrix": {
            "path": _rel(TRACEABILITY),
            "csv_path": _rel(TRACEABILITY_CSV),
            "role": "upstream_evidence_traceability",
            "sha256": _sha256_path(TRACEABILITY),
            "csv_sha256": _sha256_path(TRACEABILITY_CSV),
        },
    }

    task_context = {
        "api_signatures": ["benchmark.pricing.v1.ResolvedPriceService.AssessLines"],
        "artifact_types_addressed": ["grpc_service", "benchmark_seed_envelope"],
        "behavioral_suite_manifest_sha256": suite_manifest_sha,
        "behavioral_suite_sha256": suite_sha,
        "design_doc_sections": [
            "S1 neutral pricing brief",
            "S2 canonical proto/spec decisions",
            "S2 canonical behavioral suite manifest",
        ],
        "estimated_loc": 240,
        "feature_id": "LIFERAY-RESOLVEDPRICESERVICE",
        "language": "nodejs",
        "language_rationale": LANGUAGE_RATIONALE,
        "module_system": "commonjs",
        "negative_scope": [
            "tax calculation",
            "discount caps",
            "price-list lookup",
            "promotion discovery",
            "coupon validation or usage tracking",
            "account/channel rules",
            "inventory checks",
            "database access",
            "network calls",
            "currency conversion",
        ],
        "node_version": "20",
        "protocol": "grpc",
        "proto_filename": "pricing.proto",
        "proto_package": "benchmark.pricing.v1",
        "proto_service": "ResolvedPriceService",
        "proto_sha256": proto_sha,
        "quality_hints": [
            "Use exact decimal arithmetic for all numeric operations.",
            "Round monetary outputs only at response formatting time.",
            "Preserve input line order in the response.",
            "Return INVALID_ARGUMENT for invalid request shapes and values.",
        ],
        "rpcs": ["AssessLines"],
        "runtime_dependencies": RUNTIME_DEPENDENCIES,
        "spec_sha256": spec_sha,
        "target_files": ["src/resolvedpriceservice/server.js"],
    }

    return {
        "artifacts": artifacts,
        "benchmark_packaging": {
            "status": "seed_envelope_registered",
            "promotion_gate": (
                "Registered in hardened-index.json after adding the resolvedpriceservice "
                "behavioral suite/proto adapter."
            ),
        },
        "generator": "scripts/gen_resolved_pricing_seed.py",
        "schema_version": "1.0",
        "service_metadata": {
            "behavioral_suite_sha256": suite_sha,
            "canonical_spec_sha256": spec_sha,
            "dependencies": RUNTIME_DEPENDENCIES,
            "estimated_loc": 240,
            "language": "nodejs",
            "language_rationale": LANGUAGE_RATIONALE,
            "proto_filename": "pricing.proto",
            "proto_package": "benchmark.pricing.v1",
            "proto_service": "ResolvedPriceService",
            "proto_sha256": proto_sha,
            "rpc_count": 1,
            "rpcs": ["AssessLines"],
            "service": "resolvedpriceservice",
        },
        "startup": {
            "cmd": ["node", "src/resolvedpriceservice/server.js"],
            "port_env": "PORT",
            "readiness": "tcp",
        },
        "tasks": [
            {
                "config": {
                    "context": task_context,
                    "requirements_text": requirements_text,
                    "task_description": (
                        "Implement the ResolvedPriceService gRPC service as a pure, stateless "
                        "resolved-line pricing calculator in nodejs. AssessLines selects eligible "
                        "candidate unit prices, applies percentage and fixed reductions with exact "
                        "decimal arithmetic, handles price-on-request lines, rounds only at output "
                        "formatting, returns numeric totals, and rejects invalid requests with "
                        "INVALID_ARGUMENT. Implement exactly the one RPC defined in the embedded "
                        "pricing.proto and do not implement any other service."
                    ),
                },
                "depends_on": [],
                "task_id": "LIFERAY-RESOLVEDPRICESERVICE",
                "task_type": "task",
                "title": "ResolvedPriceService (nodejs) -- Liferay-derived resolved pricing calculator",
            }
        ],
        "version": "0.1",
    }


def _upsert_index(seed_sha: str, proto_sha: str) -> None:
    index = {
        "generator": "scripts/gen_resolved_pricing_seed.py",
        "schema_version": "1.0",
        "tier": "hardened",
        "seeds": [],
    }
    if INDEX.exists():
        index = json.loads(INDEX.read_text(encoding="utf-8"))
    entry = {
        "axes": ["B", "C", "E"],
        "derived_from": "Liferay Commerce via OpenAI/Codex bias audit canonical S2 artifacts",
        "language": "nodejs",
        "proto": "pricing.proto",
        "proto_sha256": proto_sha,
        "seed_file": OUT.name,
        "seed_sha256": seed_sha,
        "service": "resolvedpriceservice",
        "target_file": "src/resolvedpriceservice/server.js",
    }
    others = [s for s in index.get("seeds", []) if s.get("service") != "resolvedpriceservice"]
    index["seeds"] = sorted(others + [entry], key=lambda s: s["service"])
    INDEX.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    seed = build_seed()
    seed_bytes = json.dumps(seed, indent=2, sort_keys=True) + "\n"
    OUT.write_text(seed_bytes, encoding="utf-8")
    seed_sha = _sha256_text(seed_bytes)
    proto_sha = seed["service_metadata"]["proto_sha256"]
    _upsert_index(seed_sha, proto_sha)
    print(f"wrote {_rel(OUT)} (seed_sha256={seed_sha})")
    print(f"registered in {_rel(INDEX)} (seed_sha256={seed_sha[:12]})")


if __name__ == "__main__":
    main()
