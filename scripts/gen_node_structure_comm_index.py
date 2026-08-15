#!/usr/bin/env python3
"""Generate the Node/JS/TS structure -> OTel §5 communication capability index.

Node analogue of gen_go_structure_comm_index.py. ADVISORY tier (nodejs_parser regex), **imports-only**
φ: nodejs_parser drops decorators, and the Java pilot proved the annotation axis adds 0 marginal domain
coverage (annotation ⊆ import), so Node skips it by design (precision-vs-coverage lesson applied
prospectively — dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md). Import extraction lives in the ANALYZER (the
parser exposes no parse_nodejs_imports). TS's scip-typescript is CKG Phase 1 — the nearest call-site
resolution unlock of any language.

This script is now THIN: it holds Node's DATA and hands it to the shared ``startd8.coverage_map``
engine. The public helpers below are the parity test's surface (``_node_structure_forms`` …,
``RESOLUTION_PENDING``, ``build_index``, ``INDEX_DOC``).

Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md · Spec:
docs/design/REQ-crosswalk-node-structure-to-otel-comm-domains.md.

Usage:
    python3 scripts/gen_node_structure_comm_index.py
    python3 scripts/gen_node_structure_comm_index.py --check      # drift guard (exit 1 on drift)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from startd8.coverage_map import (
    LanguageIndexSpec,
    RenderSpec,
    build_index as _engine_build_index,
    index_files,
    render_index_md,
    write_or_check,
)

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "docs" / "design" / "node-capability-index"
SCHEMA_VERSION = "1.0"
GENERATOR = "gen_node_structure_comm_index.py"
PATTERN_REF = "dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md"
SPEC_REF = "docs/design/REQ-crosswalk-node-structure-to-otel-comm-domains.md"
SUBSTRATE = "nodejs_parser.py (regex, advisory-tier; imports-only φ; decorators not extracted)"
INDEX_DOC = "NODE_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md"


def _node_structure_forms() -> list[dict[str, Any]]:
    """L1 (FR-1). Forms nodejs_parser.parse_nodejs_source emits. Each parser_kind ∈ PARSER_KIND_SETS['nodejs']."""
    return [
        {"id": "NODE-STRUCT-001", "form": "function", "parser_kind": "function", "note": "function name() {}"},
        {"id": "NODE-STRUCT-002", "form": "class", "parser_kind": "class", "note": "class Name {}"},
        {"id": "NODE-STRUCT-003", "form": "method", "parser_kind": "method", "note": "method in a class body"},
        {"id": "NODE-STRUCT-004", "form": "const_function", "parser_kind": "const_function",
         "note": "const name = () => {} / const name = function(){}"},
        {"id": "NODE-STRUCT-005", "form": "interface", "parser_kind": "interface", "note": "TS interface Name {}"},
        {"id": "NODE-STRUCT-006", "form": "type_alias", "parser_kind": "type_alias", "note": "TS type Name = ..."},
    ]


def _language_composites() -> dict[str, Any]:
    """L3 (FR-3). Declaration-level idioms keyed on node_forms (NOT ast_nodes)."""
    return {
        "composites": [
            {"id": "NODE-LC-001", "name": "arrow_function_export", "node_forms": ["NODE-STRUCT-004"],
             "note": "export const f = () => {} — the dominant JS/TS handler shape"},
            {"id": "NODE-LC-002", "name": "async_function", "node_forms": ["NODE-STRUCT-001", "NODE-STRUCT-004"],
             "note": "async function / async arrow — concurrent I/O"},
            {"id": "NODE-LC-003", "name": "interface_decl", "node_forms": ["NODE-STRUCT-005"],
             "note": "TS interface — contract surface"},
            {"id": "NODE-LC-004", "name": "type_alias", "node_forms": ["NODE-STRUCT-006"],
             "note": "TS type alias"},
            {"id": "NODE-LC-005", "name": "class_method", "node_forms": ["NODE-STRUCT-002", "NODE-STRUCT-003"],
             "note": "class with methods — service/handler class"},
        ],
        "not_witnessable": [
            {"name": "promise_chain", "reason": "body-level .then()/await chains; parser doesn't parse bodies"},
            {"name": "dynamic_import", "reason": "import('x') is a body-level call expression"},
            {"name": "callback", "reason": "callback passing is body-level"},
            {"name": "decorator", "reason": "TS decorators are dropped by nodejs_parser AND add 0 domain coverage (Java IT-5)"},
        ],
    }


def _communication_crosswalk() -> list[dict[str, Any]]:
    """L4 (FR-2). φ: 15 §5 patterns → npm import specifiers. IMPORTS-ONLY (no annotation_signatures, NR-2).

    id-suffixes + semconv_domain set are key-for-key with the Python pilot. ``grounding``: corpus = in MCP/;
    ecosystem = canonical npm path, not in that corpus. Floor entries carry no signatures.
    """
    return [
        {"id": "NODE-OTEL-5.1-HTTP", "otel_pattern": "HTTP", "semconv_domain": "http",
         "grounding": "corpus", "span_kinds": ["CLIENT", "SERVER"],
         "import_signatures": ["express", "fastify", "@nestjs/common", "koa", "http", "https",
                               "node-fetch", "axios", "got", "undici"]},
        {"id": "NODE-OTEL-5.2-HTTP-METRICS", "otel_pattern": "HTTP metrics", "semconv_domain": "http",
         "floor": True, "note": "Metric emission is in call bodies; not distinguishable from plain HTTP by import."},
        {"id": "NODE-OTEL-5.3-RPC", "otel_pattern": "gRPC", "semconv_domain": "rpc",
         "grounding": "ecosystem", "span_kinds": ["CLIENT", "SERVER"],
         "import_signatures": ["@grpc/grpc-js", "grpc"]},
        {"id": "NODE-OTEL-5.3-CONNECT", "otel_pattern": "Connect RPC", "semconv_domain": "rpc",
         "grounding": "ecosystem",
         "import_signatures": ["@connectrpc/connect", "@bufbuild/connect"]},
        {"id": "NODE-OTEL-5.3-MCP", "otel_pattern": "Model Context Protocol", "semconv_domain": "mcp",
         "grounding": "corpus",
         "note": "MCP is a first-class OTel semconv namespace (JSON-RPC family); reclassified out of rpc (2026-08-15 calibration).",
         "import_signatures": ["@modelcontextprotocol/sdk"]},
        {"id": "NODE-OTEL-5.4-MESSAGING", "otel_pattern": "Messaging", "semconv_domain": "messaging",
         "grounding": "ecosystem", "span_kinds": ["PRODUCER", "CONSUMER"],
         "import_signatures": ["kafkajs", "amqplib", "nats", "@google-cloud/pubsub", "bullmq", "bull"]},
        {"id": "NODE-OTEL-5.5-DATABASE", "otel_pattern": "Database", "semconv_domain": "db",
         "grounding": "ecosystem", "span_kinds": ["CLIENT"],
         "import_signatures": ["pg", "mysql2", "mysql", "ioredis", "redis", "mongodb", "mongoose",
                               "typeorm", "@prisma/client", "knex", "sqlite3"]},
        {"id": "NODE-OTEL-5.6-GRAPHQL", "otel_pattern": "GraphQL", "semconv_domain": "graphql",
         "grounding": "ecosystem",
         "import_signatures": ["graphql", "@apollo/server", "apollo-server", "type-graphql"]},
        {"id": "NODE-OTEL-5.6-FAAS", "otel_pattern": "FaaS", "semconv_domain": "faas",
         "grounding": "ecosystem", "import_signatures": ["aws-lambda", "@vercel/node"]},
        {"id": "NODE-OTEL-5.6-FEATURE-FLAGS", "otel_pattern": "Feature flags",
         "semconv_domain": "feature-flags", "grounding": "ecosystem",
         "import_signatures": ["@openfeature/server-sdk", "launchdarkly-node-server-sdk", "unleash-client"]},
        {"id": "NODE-OTEL-5.6-GENAI", "otel_pattern": "GenAI", "semconv_domain": "gen-ai",
         "grounding": "ecosystem",
         "import_signatures": ["openai", "@anthropic-ai/sdk", "@google/generative-ai", "langchain", "@langchain/core"]},
        {"id": "NODE-OTEL-5.7-CICD", "otel_pattern": "CI/CD", "semconv_domain": "cicd", "floor": True,
         "note": "Evidenced by pipeline config + env, not an npm import."},
        {"id": "NODE-OTEL-5.7-CLI", "otel_pattern": "CLI", "semconv_domain": "cli",
         "grounding": "ecosystem",
         "import_signatures": ["commander", "yargs", "inquirer", "@oclif/core", "cac"]},
        {"id": "NODE-OTEL-5.1-DNS", "otel_pattern": "DNS", "semconv_domain": "dns",
         "grounding": "ecosystem", "import_signatures": ["dns", "dns/promises", "native-dns"]},
        {"id": "NODE-OTEL-5.1-OBJECT-STORE", "otel_pattern": "Object stores",
         "semconv_domain": "object-stores", "registry": "derived", "grounding": "ecosystem",
         "import_signatures": ["@aws-sdk/client-s3", "@google-cloud/storage", "minio"]},
        {"id": "NODE-OTEL-5.1-CLOUD-SDK", "otel_pattern": "Cloud SDK", "semconv_domain": "cloud",
         "grounding": "ecosystem",
         "import_signatures": ["aws-sdk", "@aws-sdk", "@google-cloud", "@azure"]},
    ]


def _detectability_floor() -> list[dict[str, Any]]:
    return [
        {"id": "NODE-OTEL-5.2-HTTP-METRICS", "semconv_domain": "http", "tier": "advisory",
         "reason": "Metric emission is in call bodies; the http import is already claimed by 5.1-HTTP."},
        {"id": "NODE-OTEL-5.7-CICD", "semconv_domain": "cicd", "tier": "advisory",
         "reason": "Pipeline config + env, not an npm import."},
    ]


RESOLUTION_PENDING = {
    "axis": "call-site",
    "status": "resolution-pending",
    "unlock": "SCIP (scip-typescript) — CODE_KNOWLEDGE_GRAPH_DESIGN.md Phase 1 (the NEAREST unlock of any language)",
    "note": "TS is the first SCIP indexer in the CKG roadmap, so Node's call-site φ is closest to landing.",
}


def _counts() -> dict[str, int]:
    forms = _node_structure_forms()
    crosswalk = _communication_crosswalk()
    achievable = [p for p in crosswalk if not p.get("floor")]
    return {
        "structure_forms": len(forms),
        "language_composites": len(_language_composites()["composites"]),
        "communication_patterns": len(crosswalk),
        "achievable_patterns": len(achievable),
        "floor_patterns": len(_detectability_floor()),
    }


def _render_spec() -> RenderSpec:
    """The prose + column config for the Node index .md (imports-only; no extra columns)."""
    doc = {
        "substrate": SUBSTRATE, "tier": "advisory", "pattern_ref": PATTERN_REF, "spec_ref": SPEC_REF,
        "counts": _counts(), "resolution_pending": RESOLUTION_PENDING,
    }
    c = doc["counts"]
    return RenderSpec(
        header=[
            "# Node/JS/TS Structure → OTel §5 Communication Capability Index", "",
            f"> **GENERATED by `{GENERATOR}` — do not edit.** Edit the generator's constants and re-run; "
            f"`--check` fails on any hand-edit (Kagami / single-source).", "",
            f"**Substrate:** `{doc['substrate']}`  ", f"**Tier:** {doc['tier']}  ",
            f"**Pattern:** `{doc['pattern_ref']}` · **Spec:** `{doc['spec_ref']}`  ",
            f"**Counts:** {c['structure_forms']} forms · {c['language_composites']} composites · "
            f"{c['communication_patterns']} §5 patterns ({c['achievable_patterns']} achievable + {c['floor_patterns']} floor)", "",
            "**Imports-only** by design (nodejs_parser drops decorators; Java IT-5 proved the annotation axis adds "
            f"no domain coverage). Call-site φ is **{doc['resolution_pending']['status']}** — {doc['resolution_pending']['unlock']}.", "",
        ],
        l1_heading=[
            "## L1 — Structural-element surface (`NODE-STRUCT-*`)", "",
            "| id | form | parser_kind | note |", "| --- | --- | --- | --- |",
        ],
        l1_witnessable=False,
        l1_after=[],
        l3_heading=[
            "", "## L3 — Language composites (`NODE-LC-*`, keyed on `node_forms`)", "",
            "| id | name | node_forms | note |", "| --- | --- | --- | --- |",
        ],
        forms_key="node_forms",
        l3_field_col=False,
        not_witnessable_line=lambda nw: [
            "", "**Not witnessable:** " + ", ".join(f"`{n['name']}`" for n in nw) + ".", "",
        ],
        l4_heading=[
            "## L4 — §5 communication crosswalk (`NODE-OTEL-5.*`, imports-only)", "",
            "| id | semconv | grounding | import signatures |", "| --- | --- | --- | --- |",
        ],
        l4_annotations=False,
        floor_heading=[
            "", "### Detectability floor (correct-absence, excluded from denominator)", "",
            "| id | semconv | reason |", "| --- | --- | --- |",
        ],
        footer=[
            "", f"> **Resolution-pending:** {RESOLUTION_PENDING['note']}", "",
        ],
    )


def _spec() -> LanguageIndexSpec:
    return LanguageIndexSpec(
        meta={
            "schema_version": SCHEMA_VERSION, "generator": GENERATOR, "pattern_ref": PATTERN_REF,
            "spec_ref": SPEC_REF, "substrate": SUBSTRATE, "tier": "advisory",
        },
        forms_file="node-structure-forms.json",
        structure_forms=_node_structure_forms(),
        composites=_language_composites()["composites"],
        not_witnessable=_language_composites()["not_witnessable"],
        crosswalk=_communication_crosswalk(),
        floor=_detectability_floor(),
        detector_label="import-only (advisory; no annotation axis, no call graph)",
        index_doc=INDEX_DOC,
        render=_render_spec(),
        resolution_pending=RESOLUTION_PENDING,
    )


def build_index() -> dict[str, Any]:
    return _engine_build_index(_spec())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="Verify on-disk index matches generated (exit 1 on drift)")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)

    spec = _spec()
    doc = _engine_build_index(spec)
    files = index_files(spec, doc)
    md_path = args.out_dir.parent / INDEX_DOC
    md_text = render_index_md(spec, doc)
    return write_or_check(files, args.out_dir, md_path, md_text,
                          index_doc=INDEX_DOC, generator=GENERATOR,
                          counts=doc["counts"], check=args.check)


if __name__ == "__main__":
    sys.exit(main())
