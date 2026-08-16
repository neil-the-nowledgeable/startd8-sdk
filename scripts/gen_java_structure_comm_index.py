#!/usr/bin/env python3
"""Generate the Java structure -> OTel §5 communication capability index.

Java analogue of gen_go_structure_comm_index.py. Java is authoritative-*fidelity* (javalang) but
**resolution-blind** (declaration-depth, no call graph — CODE_KNOWLEDGE_GRAPH_DESIGN.md), so the
call-site φ is a resolution-pending floor; the NEW signal Java exercises vs Go is **annotations**
(@Path/@GrpcService — declaration-attached, no body walk).

PER-PARSE TIERING (MULTILANG_MANIFEST_VALIDATION_REQUIREMENTS.md FR-5): when javalang is absent the
parser falls back to regex and that parse is *advisory* — it emits a SUBSET of the authoritative
kinds (grounded 2026-08-15: regex emits {class, interface, enum, method}; drops field/constant;
constructor→method). Each L1 form records `witnessable_at` so the parity test verifies this.

This script is now THIN: it holds Java's DATA (incl. the annotation φ axis + witnessable_at) and
hands it to the shared ``startd8.coverage_map`` engine. The public helpers below are the parity
test's surface (``_java_structure_forms`` …, ``RESOLUTION_PENDING``, ``build_index``, ``INDEX_DOC``).

Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md · Spec:
docs/design/REQ-crosswalk-java-structure-to-otel-comm-domains.md (FR-1 / FR-6, IT-1).

Usage:
    python3 scripts/gen_java_structure_comm_index.py
    python3 scripts/gen_java_structure_comm_index.py --check      # drift guard (exit 1 on drift)
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
OUT_DIR = REPO / "docs" / "design" / "java-capability-index"
SCHEMA_VERSION = "1.0"
GENERATOR = "gen_java_structure_comm_index.py"
PATTERN_REF = "dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md"
SPEC_REF = "docs/design/REQ-crosswalk-java-structure-to-otel-comm-domains.md"
#: authoritative FIDELITY (javalang) but resolution-blind; regex-fallback when javalang absent.
SUBSTRATE = "java_parser.py (javalang when available, regex fallback; declaration-depth; annotations)"
TIER = "authoritative-fidelity (per-parse: advisory when javalang absent)"

#: The human-readable index doc (IT-4). Regenerated from JSON, NEVER hand-edited (Kagami).
INDEX_DOC = "JAVA_STRUCTURE_COMMUNICATION_CAPABILITY_INDEX.md"


def _java_structure_forms() -> list[dict[str, Any]]:
    """L1 (FR-1). The structural-element surface parse_java_source recognizes.

    HAND-AUTHORED. Each ``parser_kind`` MUST be in PARSER_KIND_SETS["java"] (parity test enforces).
    ``witnessable_at``: "both" = emitted on the regex-fallback path too; "authoritative" = only under
    javalang (the regex path drops/misclassifies it — grounded per-parse tiering, FR-5).
    """
    return [
        {"id": "JAVA-STRUCT-001", "form": "class", "parser_kind": "class",
         "witnessable_at": "both", "note": "class Name { ... }"},
        {"id": "JAVA-STRUCT-002", "form": "interface", "parser_kind": "interface",
         "witnessable_at": "both", "note": "interface Name { ... }"},
        {"id": "JAVA-STRUCT-003", "form": "enum", "parser_kind": "enum",
         "witnessable_at": "both", "note": "enum Name { ... }"},
        {"id": "JAVA-STRUCT-004", "form": "method", "parser_kind": "method",
         "witnessable_at": "both", "note": "returnType name(params); annotations attach here"},
        {"id": "JAVA-STRUCT-005", "form": "constructor", "parser_kind": "constructor",
         "witnessable_at": "authoritative",
         "note": "Name(params) {}; the regex path emits it as kind='method'"},
        {"id": "JAVA-STRUCT-006", "form": "field", "parser_kind": "field",
         "witnessable_at": "authoritative", "note": "instance field; dropped on the regex path"},
        {"id": "JAVA-STRUCT-007", "form": "constant", "parser_kind": "constant",
         "witnessable_at": "authoritative",
         "note": "static final field; dropped on the regex path"},
    ]


def _communication_crosswalk() -> list[dict[str, Any]]:
    """L4 (FR-2). φ: the 15 OTel §5 patterns → Java signals. NEW vs Go: annotation_signatures.

    INVARIANT: id-suffixes + semconv_domain set are key-for-key with the Python pilot. Detector is
    IMPORT + ANNOTATION (declaration-attached; no call graph — resolution-pending, SCIP-java/CKG).
    ``grounding``: corpus = imported/annotated in OSS/kestra or OSS/Istio (verified 2026-08-15);
    ecosystem = canonical Java path, not in that corpus. Floor entries carry no signatures.
    """
    return [
        {"id": "JAVA-OTEL-5.1-HTTP", "otel_pattern": "HTTP", "semconv_domain": "http",
         "grounding": "corpus", "span_kinds": ["CLIENT", "SERVER"],
         "import_signatures": ["javax.ws.rs", "jakarta.ws.rs", "io.micronaut.http",
                               "org.springframework.web", "io.javalin", "spark"],
         "annotation_signatures": ["Path", "GET", "Get", "POST", "Post", "PUT", "DELETE",
                                   "RestController", "RequestMapping", "GetMapping", "PostMapping",
                                   "Controller"]},
        {"id": "JAVA-OTEL-5.2-HTTP-METRICS", "otel_pattern": "HTTP metrics",
         "semconv_domain": "http", "floor": True,
         "note": "Metric emission is in call bodies; not distinguishable from plain HTTP by import/annotation."},
        {"id": "JAVA-OTEL-5.3-RPC", "otel_pattern": "gRPC", "semconv_domain": "rpc",
         "grounding": "corpus", "span_kinds": ["CLIENT", "SERVER"],
         "import_signatures": ["io.grpc"], "annotation_signatures": ["GrpcService", "GrpcClient"]},
        {"id": "JAVA-OTEL-5.3-CONNECT", "otel_pattern": "Connect RPC", "semconv_domain": "rpc",
         "grounding": "ecosystem",
         "import_signatures": ["com.connectrpc", "build.buf.connect"], "annotation_signatures": []},
        {"id": "JAVA-OTEL-5.3-MCP", "otel_pattern": "Model Context Protocol", "semconv_domain": "mcp",
         "grounding": "ecosystem",
         "import_signatures": ["io.modelcontextprotocol"], "annotation_signatures": []},
        {"id": "JAVA-OTEL-5.4-MESSAGING", "otel_pattern": "Messaging", "semconv_domain": "messaging",
         "grounding": "corpus", "span_kinds": ["PRODUCER", "CONSUMER"],
         "import_signatures": ["org.apache.kafka", "org.springframework.kafka", "javax.jms",
                               "jakarta.jms", "io.nats"],
         "annotation_signatures": ["KafkaListener", "JmsListener"]},
        {"id": "JAVA-OTEL-5.5-DATABASE", "otel_pattern": "Database", "semconv_domain": "db",
         "grounding": "corpus", "span_kinds": ["CLIENT"],
         "import_signatures": ["java.sql", "javax.sql", "org.springframework.data",
                               "jakarta.persistence", "javax.persistence", "org.hibernate",
                               "com.mongodb", "io.micronaut.data"],
         "annotation_signatures": ["Repository", "Entity", "Table", "Query"]},
        {"id": "JAVA-OTEL-5.6-GRAPHQL", "otel_pattern": "GraphQL", "semconv_domain": "graphql",
         "grounding": "ecosystem",
         "import_signatures": ["graphql", "com.netflix.graphql", "org.springframework.graphql"],
         "annotation_signatures": ["SchemaMapping", "QueryMapping", "MutationMapping"]},
        {"id": "JAVA-OTEL-5.6-FAAS", "otel_pattern": "FaaS", "semconv_domain": "faas",
         "grounding": "ecosystem",
         "import_signatures": ["com.amazonaws.services.lambda"], "annotation_signatures": []},
        {"id": "JAVA-OTEL-5.6-FEATURE-FLAGS", "otel_pattern": "Feature flags",
         "semconv_domain": "feature-flags", "grounding": "ecosystem",
         "import_signatures": ["dev.openfeature", "com.launchdarkly"], "annotation_signatures": []},
        {"id": "JAVA-OTEL-5.6-GENAI", "otel_pattern": "GenAI", "semconv_domain": "gen-ai",
         "grounding": "ecosystem",
         "note": "Import-detectable (SDK import = domain hypothesis) — NOT floor.",
         "import_signatures": ["dev.langchain4j", "com.theokanning.openai", "com.azure.ai.openai",
                               "com.openai"], "annotation_signatures": []},
        {"id": "JAVA-OTEL-5.7-CICD", "otel_pattern": "CI/CD", "semconv_domain": "cicd", "floor": True,
         "note": "Evidenced by pipeline config + env (CI/GITHUB_ACTIONS), not a Java import/annotation."},
        {"id": "JAVA-OTEL-5.7-CLI", "otel_pattern": "CLI", "semconv_domain": "cli",
         "grounding": "corpus",
         "import_signatures": ["picocli", "org.apache.commons.cli", "com.beust.jcommander"],
         "annotation_signatures": ["Command"]},
        {"id": "JAVA-OTEL-5.1-DNS", "otel_pattern": "DNS", "semconv_domain": "dns",
         "grounding": "ecosystem",
         "note": "stdlib java.net excluded (broad — collides with http); specific signal is a DNS lib.",
         "import_signatures": ["org.xbill.DNS", "io.netty.resolver.dns"], "annotation_signatures": []},
        {"id": "JAVA-OTEL-5.1-OBJECT-STORE", "otel_pattern": "Object stores",
         "semconv_domain": "object-stores", "registry": "derived", "grounding": "ecosystem",
         "import_signatures": ["com.amazonaws.services.s3", "software.amazon.awssdk.services.s3",
                               "com.google.cloud.storage", "io.minio"], "annotation_signatures": []},
        {"id": "JAVA-OTEL-5.1-CLOUD-SDK", "otel_pattern": "Cloud SDK",
         "semconv_domain": "cloud", "grounding": "ecosystem",
         "import_signatures": ["com.amazonaws", "software.amazon.awssdk", "com.google.cloud",
                               "com.azure"], "annotation_signatures": []},
    ]


def _detectability_floor() -> list[dict[str, Any]]:
    """FR-5. Patterns the static import+annotation detector cannot witness (correct-absence)."""
    return [
        {"id": "JAVA-OTEL-5.2-HTTP-METRICS", "semconv_domain": "http", "tier": "advisory",
         "reason": "Metric emission is in call bodies (java_parser is resolution-blind); the http "
                   "import/annotation is already claimed by 5.1-HTTP."},
        {"id": "JAVA-OTEL-5.7-CICD", "semconv_domain": "cicd", "tier": "advisory",
         "reason": "Pipeline config + env, not a Java import/annotation — nothing to match."},
    ]


#: The call-site φ AXIS (detecting invocations, not just imports/annotations) is deferred, not absent.
RESOLUTION_PENDING = {
    "axis": "call-site",
    "status": "resolution-pending",
    "unlock": "SCIP (scip-java) — CODE_KNOWLEDGE_GRAPH_DESIGN.md Phase 4",
    "note": "No §5 domain currently depends on it — import+annotation covers all 13 achievable — so "
            "there are no per-pattern resolution-pending floor entries; this records the deferred capability.",
}


def _language_composites() -> dict[str, Any]:
    """L3 (FR-3). Java idiom clusters — keyed on ``java_forms`` (JAVA-STRUCT ids), NOT ast_nodes.

    Declaration-level only (java_parser is resolution-blind). Each keys on a real ``JavaElement``
    field (annotations / extends / implements — all populated on the regex path). Body-level idioms
    go in ``not_witnessable``.
    """
    return {
        "composites": [
            {"id": "JAVA-LC-001", "name": "annotated_type", "java_forms": ["JAVA-STRUCT-001", "JAVA-STRUCT-002", "JAVA-STRUCT-003"],
             "field": "annotations", "note": "type carrying annotations — the framework surface (@Path, @Entity …)"},
            {"id": "JAVA-LC-002", "name": "annotation_bearing_method", "java_forms": ["JAVA-STRUCT-004"],
             "field": "annotations", "note": "method carrying annotations (@GET, @KafkaListener …)"},
            {"id": "JAVA-LC-003", "name": "interface_impl", "java_forms": ["JAVA-STRUCT-001"],
             "field": "implements", "note": "class implements interface(s) (JavaElement.implements)"},
            {"id": "JAVA-LC-004", "name": "subclass", "java_forms": ["JAVA-STRUCT-001"],
             "field": "extends", "note": "class extends a base (JavaElement.extends)"},
            {"id": "JAVA-LC-005", "name": "enum_type", "java_forms": ["JAVA-STRUCT-003"],
             "field": "kind", "note": "enumerated type"},
        ],
        "not_witnessable": [
            {"name": "lambda_expression", "reason": "body-level; java_parser does not parse method bodies"},
            {"name": "try_with_resources", "reason": "body-level statement"},
            {"name": "stream_pipeline", "reason": "body-level call chain (resolution-pending)"},
            {"name": "generic_type_params", "reason": "java_parser does not expose type parameters"},
            {"name": "nested_class_relation", "reason": "the regex path flattens nesting (no parent link)"},
        ],
    }


def _counts() -> dict[str, int]:
    forms = _java_structure_forms()
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
    """The prose + column config for the Java index .md (annotation + witnessable_at columns on)."""
    doc = {
        "substrate": SUBSTRATE, "tier": TIER, "pattern_ref": PATTERN_REF, "spec_ref": SPEC_REF,
        "counts": _counts(), "resolution_pending": RESOLUTION_PENDING,
    }
    c = doc["counts"]
    return RenderSpec(
        header=[
            "# Java Structure → OTel §5 Communication Capability Index",
            "",
            f"> **GENERATED by `{GENERATOR}` — do not edit.** Edit the generator's constants and re-run; "
            f"`--check` fails on any hand-edit (Kagami / single-source).",
            "",
            f"**Substrate:** `{doc['substrate']}`  ",
            f"**Tier:** {doc['tier']}  ",
            f"**Pattern:** `{doc['pattern_ref']}` · **Spec:** `{doc['spec_ref']}`  ",
            f"**Counts:** {c['structure_forms']} forms · {c['language_composites']} composites · "
            f"{c['communication_patterns']} §5 patterns ({c['achievable_patterns']} achievable + {c['floor_patterns']} floor)",
            "",
            "The Java instantiation of the coverage-map pattern. **New vs Go: the annotation φ axis** — a §5 "
            "pattern fires on an import **or** a declaration-attached annotation. Java is resolution-blind "
            f"(no call graph); the call-site axis is **{doc['resolution_pending']['status']}** "
            f"({doc['resolution_pending']['unlock']}).",
            "",
        ],
        l1_heading=[
            "## L1 — Structural-element surface (`JAVA-STRUCT-*`)",
            "",
            "| id | form | parser_kind | witnessable_at | note |",
            "| --- | --- | --- | --- | --- |",
        ],
        l1_witnessable=True,
        l1_after=[
            "", "> `witnessable_at=authoritative` forms need javalang; the regex-fallback path drops them "
            "(per-parse tiering, MULTILANG_MANIFEST_VALIDATION FR-5).", "",
        ],
        l3_heading=[
            "## L3 — Language composites (`JAVA-LC-*`, keyed on `java_forms`)", "",
            "| id | name | java_forms | field | note |", "| --- | --- | --- | --- | --- |",
        ],
        forms_key="java_forms",
        l3_field_col=True,
        not_witnessable_line=lambda nw: [
            "", "**Not witnessable** (body-level / not exposed): "
            + ", ".join(f"`{n['name']}`" for n in nw) + ".", "",
        ],
        l4_heading=[
            "## L4 — §5 communication crosswalk (`JAVA-OTEL-5.*`)", "",
            "Detector is **import + annotation**. `grounding`: corpus = in OSS/kestra·Istio; ecosystem = canonical Java path.", "",
            "| id | semconv | grounding | import signatures | annotation signatures |",
            "| --- | --- | --- | --- | --- |",
        ],
        l4_annotations=True,
        floor_heading=[
            "", "### Detectability floor (correct-absence, excluded from denominator)", "",
            "| id | semconv | reason |", "| --- | --- | --- |",
        ],
        footer=[
            "", f"> **Resolution-pending axis:** {RESOLUTION_PENDING['note']}", "",
        ],
    )


def _spec() -> LanguageIndexSpec:
    return LanguageIndexSpec(
        meta={
            "schema_version": SCHEMA_VERSION, "generator": GENERATOR, "pattern_ref": PATTERN_REF,
            "spec_ref": SPEC_REF, "substrate": SUBSTRATE, "tier": TIER,
        },
        forms_file="java-structure-forms.json",
        structure_forms=_java_structure_forms(),
        composites=_language_composites()["composites"],
        not_witnessable=_language_composites()["not_witnessable"],
        crosswalk=_communication_crosswalk(),
        floor=_detectability_floor(),
        detector_label="import + annotation (declaration-attached; no call graph)",
        index_doc=INDEX_DOC,
        render=_render_spec(),
        resolution_pending=RESOLUTION_PENDING,
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
