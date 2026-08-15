#!/usr/bin/env python3
"""Generate the Go structure -> OTel §5 communication capability index.

Go analogue of gen_python_ast_capability_index.py. ADVISORY tier: Go's structural surface
comes from the regex parser startd8/languages/go_parser.py (no AST reflection, no call graph),
so unlike the Python generator the L1 layer is a HAND-AUTHORED constant, guarded by --check
drift detection + a parity test (tests/unit/languages/test_go_index_parity.py) asserting the
authored forms stay within what the parser actually emits (PARSER_KIND_SETS["go"]).

This script is now THIN: it holds Go's coverage-map DATA and hands it to the shared engine
``startd8.coverage_map`` (serialize / drift-guard / render / build). The public helpers below
(``_go_structure_forms`` …, ``build_index``, ``INDEX_DOC``) are the parity test's surface.

Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md · Spec:
docs/design/REQ-crosswalk-go-structure-to-otel-comm-domains.md (FR-1 / FR-6, IT-1).

Layers landed incrementally (one cell per commit):
  IT-1 (this): L1 go-structure-forms.json  ← FR-1
  IT-2: language-composites.json           ← FR-3
  IT-3: communication-crosswalk.json + floor← FR-2 / FR-5

Usage:
    python3 scripts/gen_go_structure_comm_index.py            # write
    python3 scripts/gen_go_structure_comm_index.py --check    # drift guard (exit 1 on drift)
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
OUT_DIR = REPO / "docs" / "design" / "go-capability-index"
SCHEMA_VERSION = "1.0"
GENERATOR = "gen_go_structure_comm_index.py"
PATTERN_REF = "dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md"
SPEC_REF = "docs/design/REQ-crosswalk-go-structure-to-otel-comm-domains.md"
#: Extraction substrate: startd8/languages/go_parser.py, ADVISORY (regex) tier.
SUBSTRATE = "go_parser.py (regex, advisory-tier; no call graph)"

#: The human-readable index doc (IT-4). Regenerated from the JSON, NEVER hand-edited (Kagami).
INDEX_DOC = "GO_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md"


def _go_structure_forms() -> list[dict[str, Any]]:
    """L1 (FR-1). The structural-element surface go_parser.parse_go_source recognizes.

    HAND-AUTHORED (Go has no in-process reflectable grammar). Each form's ``parser_kind`` MUST
    be a member of PARSER_KIND_SETS["go"] — the parity test enforces this. struct and interface
    share parser_kind="class"; the ``discriminator`` names the GoElement field that splits them.
    """
    return [
        {
            "id": "GO-STRUCT-001", "form": "function", "parser_kind": "function",
            "go_element": "kind='function'",
            "note": "Top-level func Name(params) ret",
        },
        {
            "id": "GO-STRUCT-002", "form": "method", "parser_kind": "method",
            "go_element": "kind='method' (parent_type=receiver)",
            "note": "func (r *T) Name(...); receiver in parent_type",
        },
        {
            "id": "GO-STRUCT-003", "form": "struct", "parser_kind": "class",
            "go_element": "kind='class', is_interface=False",
            "discriminator": "is_interface=False",
            "note": "type X struct { ... }; embedded types in bases[]",
        },
        {
            "id": "GO-STRUCT-004", "form": "interface", "parser_kind": "class",
            "go_element": "kind='class', is_interface=True",
            "discriminator": "is_interface=True",
            "note": "type X interface { ... }; methods in interface_methods[]",
        },
        {
            "id": "GO-STRUCT-005", "form": "type_alias", "parser_kind": "type_alias",
            "go_element": "kind='type_alias'",
            "note": "type X = Y / type X Y",
        },
        {
            "id": "GO-STRUCT-006", "form": "constant", "parser_kind": "constant",
            "go_element": "kind='constant'",
            "note": "const X = ...",
        },
        {
            "id": "GO-STRUCT-007", "form": "variable", "parser_kind": "variable",
            "go_element": "kind='variable'",
            "note": "var X ...",
        },
    ]


def _communication_crosswalk() -> list[dict[str, Any]]:
    """L4 (FR-2 / FR-5). φ: the 15 OTel §5 patterns → Go-ecosystem import signatures.

    INVARIANT: the pattern id-suffixes and semconv_domain set are key-for-key identical to the
    Python pilot (docs/design/python-capability-index/communication-crosswalk.json) — parity
    enforced by the test. What differs is the language: signatures are Go import paths, and the
    detector is IMPORT-ONLY (advisory tier has no call graph — see _detectability_floor).

    ``grounding``: "corpus" = the signature is directly imported in OSS/Thanos or OSS/Istio
    (verified 2026-08-15); "ecosystem" = canonical Go path, not directly imported in that corpus
    (usually behind a vendored abstraction). Floor patterns carry NO import_signatures.
    """
    return [
        {
            "id": "GO-OTEL-5.1-HTTP", "otel_pattern": "HTTP", "semconv_domain": "http",
            "grounding": "corpus", "span_kinds": ["CLIENT", "SERVER"],
            "import_signatures": [
                "net/http", "github.com/gin-gonic/gin", "github.com/gorilla/mux",
                "github.com/go-chi/chi", "github.com/labstack/echo",
            ],
        },
        {
            "id": "GO-OTEL-5.2-HTTP-METRICS", "otel_pattern": "HTTP metrics",
            "semconv_domain": "http", "floor": True,
            "note": "Metric emission (http.server.request.duration) lives in instrumentation "
                    "call bodies; not distinguishable from plain HTTP by import. See detectability_floor.",
        },
        {
            "id": "GO-OTEL-5.3-RPC", "otel_pattern": "gRPC", "semconv_domain": "rpc",
            "grounding": "corpus", "span_kinds": ["CLIENT", "SERVER"],
            "import_signatures": ["google.golang.org/grpc"],
        },
        {
            "id": "GO-OTEL-5.3-CONNECT", "otel_pattern": "Connect RPC", "semconv_domain": "rpc",
            "grounding": "ecosystem",
            "import_signatures": ["connectrpc.com/connect", "github.com/bufbuild/connect-go"],
        },
        {
            "id": "GO-OTEL-5.3-MCP", "otel_pattern": "Model Context Protocol",
            "semconv_domain": "mcp", "grounding": "ecosystem",
            "import_signatures": ["github.com/mark3labs/mcp-go"],
        },
        {
            "id": "GO-OTEL-5.4-MESSAGING", "otel_pattern": "Messaging",
            "semconv_domain": "messaging", "grounding": "ecosystem",
            "span_kinds": ["PRODUCER", "CONSUMER"],
            "import_signatures": [
                "github.com/Shopify/sarama", "github.com/IBM/sarama",
                "github.com/segmentio/kafka-go", "github.com/nats-io/nats.go",
                "github.com/rabbitmq/amqp091-go",
            ],
        },
        {
            "id": "GO-OTEL-5.5-DATABASE", "otel_pattern": "Database", "semconv_domain": "db",
            "grounding": "ecosystem", "span_kinds": ["CLIENT"],
            "import_signatures": [
                "database/sql", "github.com/jackc/pgx/v5", "github.com/redis/go-redis/v9",
                "github.com/go-redis/redis", "gorm.io/gorm", "go.mongodb.org/mongo-driver",
            ],
        },
        {
            "id": "GO-OTEL-5.6-GRAPHQL", "otel_pattern": "GraphQL", "semconv_domain": "graphql",
            "grounding": "ecosystem",
            "import_signatures": [
                "github.com/graph-gophers/graphql-go", "github.com/99designs/gqlgen",
            ],
        },
        {
            "id": "GO-OTEL-5.6-FAAS", "otel_pattern": "FaaS", "semconv_domain": "faas",
            "grounding": "ecosystem",
            "import_signatures": ["github.com/aws/aws-lambda-go/lambda"],
        },
        {
            "id": "GO-OTEL-5.6-FEATURE-FLAGS", "otel_pattern": "Feature flags",
            "semconv_domain": "feature-flags", "grounding": "ecosystem",
            "import_signatures": [
                "github.com/open-feature/go-sdk",
                "github.com/launchdarkly/go-server-sdk",
                "github.com/open-feature/go-sdk-contrib/providers/flagd",
            ],
        },
        {
            "id": "GO-OTEL-5.6-GENAI", "otel_pattern": "GenAI", "semconv_domain": "gen-ai",
            "grounding": "ecosystem",
            "note": "Import-detectable at advisory tier by the SAME standard as every other domain "
                    "(SDK import = domain hypothesis); NOT a floor pattern (reclassified from the REQ).",
            "import_signatures": [
                "github.com/sashabaranov/go-openai",
                "github.com/anthropics/anthropic-sdk-go",
                "github.com/google/generative-ai-go",
            ],
        },
        {
            "id": "GO-OTEL-5.7-CICD", "otel_pattern": "CI/CD", "semconv_domain": "cicd",
            "floor": True,
            "note": "CI/CD context is evidenced by pipeline config + env (CI, GITHUB_ACTIONS), "
                    "not a Go library import. Advisory tier cannot witness it. See detectability_floor.",
        },
        {
            "id": "GO-OTEL-5.7-CLI", "otel_pattern": "CLI", "semconv_domain": "cli",
            "grounding": "corpus",
            "import_signatures": [
                "github.com/spf13/cobra", "github.com/spf13/pflag",
                "github.com/urfave/cli", "flag",
            ],
        },
        {
            "id": "GO-OTEL-5.1-DNS", "otel_pattern": "DNS", "semconv_domain": "dns",
            "grounding": "corpus",
            "note": "stdlib 'net' is intentionally EXCLUDED — under prefix matching it collides with "
                    "net/http (5.1-HTTP); github.com/miekg/dns is the specific, non-colliding signal.",
            "import_signatures": ["github.com/miekg/dns"],
        },
        {
            "id": "GO-OTEL-5.1-OBJECT-STORE", "otel_pattern": "Object stores",
            "semconv_domain": "object-stores", "registry": "derived", "grounding": "corpus",
            "import_signatures": [
                "github.com/thanos-io/objstore", "github.com/aws/aws-sdk-go/service/s3",
                "github.com/aws/aws-sdk-go-v2/service/s3", "cloud.google.com/go/storage",
                "github.com/minio/minio-go",
            ],
        },
        {
            "id": "GO-OTEL-5.1-CLOUD-SDK", "otel_pattern": "Cloud SDK",
            "semconv_domain": "cloud", "grounding": "corpus",
            "import_signatures": [
                "github.com/aws/aws-sdk-go", "github.com/aws/aws-sdk-go-v2",
                "cloud.google.com/go", "github.com/Azure/azure-sdk-for-go",
            ],
        },
    ]


def _detectability_floor() -> list[dict[str, Any]]:
    """FR-5. §5 patterns the advisory (import-only, no-call-graph) tier cannot statically witness.

    A floor entry is a CORRECT-ABSENCE, not a coverage gap: it exists in the algebra but the
    substrate structurally can't see it. Coverage excludes these from the achievable denominator.
    """
    return [
        {
            "id": "GO-OTEL-5.2-HTTP-METRICS", "semconv_domain": "http", "tier": "advisory",
            "reason": "Metric emission lives in instrumentation call bodies; go_parser.py does not "
                      "parse bodies, and the http import alone is already claimed by 5.1-HTTP.",
        },
        {
            "id": "GO-OTEL-5.7-CICD", "semconv_domain": "cicd", "tier": "advisory",
            "reason": "Evidenced by pipeline config + env vars (CI/GITHUB_ACTIONS), not a Go "
                      "library import — nothing for an import-only detector to match.",
        },
    ]


def _language_composites() -> dict[str, Any]:
    """L3 (FR-3). Go idiom clusters — keyed on ``go_forms`` (GO-STRUCT ids), NOT ast_nodes.

    SUBSTRATE FLOOR (same friction as L4): go_parser.py parses only DECLARATIONS, not bodies, so
    the only witnessable composites are declaration-level. Body-level idioms (goroutine, channel,
    defer) have no GO-STRUCT form and are recorded in ``not_witnessable`` — a correct-absence, not
    an omission. (This corrects the REQ v0.2 FR-3 list, which named those three as composites.)
    """
    return {
        "composites": [
            {
                "id": "GO-LC-001", "name": "receiver_method", "go_forms": ["GO-STRUCT-002"],
                "note": "func (r T) M(): method bound to a receiver type (GoElement.parent_type)",
            },
            {
                "id": "GO-LC-002", "name": "pointer_receiver", "go_forms": ["GO-STRUCT-002"],
                "note": "method with *T receiver (GoElement.is_pointer_receiver) — mutation/identity idiom",
            },
            {
                "id": "GO-LC-003", "name": "struct_embedding", "go_forms": ["GO-STRUCT-003"],
                "note": "type X struct { Embedded }: composition via embedded types (GoElement.bases)",
            },
            {
                "id": "GO-LC-004", "name": "interface_contract", "go_forms": ["GO-STRUCT-004"],
                "note": "interface declaring a method set (GoElement.interface_methods)",
            },
            {
                "id": "GO-LC-005", "name": "exported_api", "go_forms": [f"GO-STRUCT-00{n}" for n in range(1, 8)],
                "note": "Capitalized identifier = package-exported public surface (GoElement.is_exported)",
            },
        ],
        "not_witnessable": [
            {"name": "goroutine", "reason": "go <expr> is a body statement; go_parser does not parse bodies"},
            {"name": "channel", "reason": "chan types / <- ops live in bodies + signatures the parser doesn't decompose"},
            {"name": "defer", "reason": "defer <call> is a body statement; not a declaration form"},
            {"name": "interface_satisfaction",
             "reason": "requires cross-element method-set matching (Hitsuzen-derivable), not a single-element form"},
        ],
    }


def _counts() -> dict[str, int]:
    forms = _go_structure_forms()
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
    """The prose + column config for the Go index .md (per-language English lives here, as data)."""
    doc = {
        "substrate": SUBSTRATE, "tier": "advisory",
        "pattern_ref": PATTERN_REF, "spec_ref": SPEC_REF, "counts": _counts(),
    }
    c = doc["counts"]
    return RenderSpec(
        header=[
            "# Go Structure → OTel §5 Communication Capability Index",
            "",
            f"> **GENERATED by `{GENERATOR}` — do not edit.** Edit the generator's constants and re-run; "
            f"`--check` fails on any hand-edit (Kagami / single-source).",
            "",
            f"**Substrate:** `{doc['substrate']}` · **Tier:** {doc['tier']} (import-only; no call graph)  ",
            f"**Pattern:** `{doc['pattern_ref']}` · **Spec:** `{doc['spec_ref']}`  ",
            f"**Counts:** {c['structure_forms']} structure forms · {c['language_composites']} composites · "
            f"{c['communication_patterns']} §5 patterns ({c['achievable_patterns']} achievable + {c['floor_patterns']} floor)",
            "",
            "The Go instantiation of the four-layer coverage-map pattern. **Invariant:** L4 crosswalks to the "
            "SAME 15 OTel §5 semconv domains as the Python pilot; only the language + extraction substrate differ.",
            "",
        ],
        l1_heading=[
            "## L1 — Structural-element surface (`GO-STRUCT-*`)",
            "",
            "| id | form | parser_kind | note |",
            "| --- | --- | --- | --- |",
        ],
        l1_witnessable=False,
        l1_after=[""],
        l3_heading=[
            "## L3 — Language composites (`GO-LC-*`, keyed on `go_forms`)", "",
            "| id | name | go_forms | note |", "| --- | --- | --- | --- |",
        ],
        forms_key="go_forms",
        l3_field_col=False,
        not_witnessable_line=lambda nw: [
            "", "**Not witnessable at advisory tier** (body-level / cross-element — correct-absence): "
            + ", ".join(f"`{n['name']}`" for n in nw) + ".", "",
        ],
        l4_heading=[
            "## L4 — §5 communication crosswalk (`GO-OTEL-5.*`)", "",
            "Detector is **import-only**. `grounding`: corpus = directly imported in OSS/Thanos·Istio; "
            "ecosystem = canonical Go path, not in that corpus.", "",
            "| id | semconv | grounding | import signatures |", "| --- | --- | --- | --- |",
        ],
        l4_annotations=False,
        floor_heading=[
            "", "### Detectability floor (un-witnessable — correct-absence, excluded from denominator)", "",
            "| id | semconv | reason |", "| --- | --- | --- |",
        ],
        footer=[
            "", "> Coverage baselines are produced by `analyze_go_comm_coverage.py` "
            "(`go-capability-index/thanos-coverage.md`), not this generator.", "",
        ],
    )


def _spec() -> LanguageIndexSpec:
    return LanguageIndexSpec(
        meta={
            "schema_version": SCHEMA_VERSION, "generator": GENERATOR, "pattern_ref": PATTERN_REF,
            "spec_ref": SPEC_REF, "substrate": SUBSTRATE, "tier": "advisory",
        },
        forms_file="go-structure-forms.json",
        structure_forms=_go_structure_forms(),
        composites=_language_composites()["composites"],
        not_witnessable=_language_composites()["not_witnessable"],
        crosswalk=_communication_crosswalk(),
        floor=_detectability_floor(),
        detector_label="import-only (advisory tier; no call graph)",
        index_doc=INDEX_DOC,
        render=_render_spec(),
    )


def build_index() -> dict[str, Any]:
    return _engine_build_index(_spec())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="Verify on-disk index matches generated (exit 1 on drift)")
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
