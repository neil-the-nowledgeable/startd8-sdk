#!/usr/bin/env python3
"""Generate the Python AST + OTel §5 communication capability index (machine-readable).

Writes numbered catalogs under ``docs/design/python-capability-index/``:
  - ``ast-nodes.json``       — stdlib ``ast`` node types (fields, category)
  - ``manifest-kinds.json``  — code_manifest ElementKind ↔ AST mapping
  - ``communication-crosswalk.json`` — OTel landscape §5 ↔ Python detections
  - ``index-meta.json``      — schema version, python version, counts

The human-readable catalog is
``docs/design/PYTHON_AST_COMMUNICATION_CAPABILITY_INDEX.md``.

Usage:
    python3 scripts/gen_python_ast_capability_index.py
    python3 scripts/gen_python_ast_capability_index.py --check
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "docs" / "design" / "python-capability-index"
SCHEMA_VERSION = "1.0"
GENERATOR = "gen_python_ast_capability_index.py"
LANDSCAPE_REF = "docs/design/OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md"


def _node_category(name: str, cls: type) -> str:
    if name in ("Module", "Interactive", "Expression", "FunctionType"):
        return "compile_unit"
    if issubclass(cls, ast.stmt):
        return "statement"
    if issubclass(cls, ast.expr):
        return "expression"
    if issubclass(cls, ast.mod):
        return "module_root"
    if issubclass(cls, ast.slice):
        return "slice"
    if issubclass(cls, ast.cmpop):
        return "cmpop"
    if issubclass(cls, ast.boolop):
        return "boolop"
    if issubclass(cls, ast.operator):
        return "operator"
    if issubclass(cls, ast.unaryop):
        return "unaryop"
    if issubclass(cls, ast.excepthandler):
        return "excepthandler"
    if issubclass(cls, ast.comprehension):
        return "comprehension"
    if issubclass(cls, ast.match_case):
        return "pattern_match"
    if issubclass(cls, ast.pattern):
        return "pattern"
    if issubclass(cls, ast.type_param):
        return "type_param"
    return "other"


def _build_ast_nodes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    idx = 1
    for name in sorted(dir(ast)):
        obj = getattr(ast, name)
        if not isinstance(obj, type) or not issubclass(obj, ast.AST) or obj is ast.AST:
            continue
        fields = list(getattr(obj, "_fields", ()))
        category = _node_category(name, obj)
        rows.append(
            {
                "id": f"PY-AST-{idx:03d}",
                "name": name,
                "category": category,
                "fields": fields,
                "doc": (obj.__doc__ or "").strip().split("\n")[0] if obj.__doc__ else "",
            }
        )
        idx += 1
    return rows


def _manifest_kinds() -> list[dict[str, Any]]:
    """StartD8 code_manifest ElementKind values produced from Python AST."""
    return [
        {
            "id": "PY-MAN-001",
            "kind": "class",
            "ast_nodes": ["ClassDef"],
            "landscape_role": "SERVER/RPC handler container; HTTP route class",
        },
        {
            "id": "PY-MAN-002",
            "kind": "function",
            "ast_nodes": ["FunctionDef"],
            "landscape_role": "Top-level callable; CLI entry (§5.7), FaaS handler (§5.6)",
        },
        {
            "id": "PY-MAN-003",
            "kind": "async_function",
            "ast_nodes": ["AsyncFunctionDef"],
            "landscape_role": "Async HTTP/RPC/messaging client or server",
        },
        {
            "id": "PY-MAN-004",
            "kind": "method",
            "ast_nodes": ["FunctionDef"],
            "landscape_role": "Service method; gRPC servicer RPC (§5.3)",
        },
        {
            "id": "PY-MAN-005",
            "kind": "async_method",
            "ast_nodes": ["AsyncFunctionDef"],
            "landscape_role": "Async service method (aiohttp/FastAPI/aiokafka)",
        },
        {
            "id": "PY-MAN-006",
            "kind": "property",
            "ast_nodes": ["FunctionDef"],
            "landscape_role": "Internal; rarely a communication boundary",
        },
        {
            "id": "PY-MAN-007",
            "kind": "constant",
            "ast_nodes": ["Assign", "AnnAssign"],
            "landscape_role": "Config (URLs, topic names, DSN strings)",
        },
        {
            "id": "PY-MAN-008",
            "kind": "variable",
            "ast_nodes": ["Assign", "AnnAssign", "NamedExpr"],
            "landscape_role": "Runtime state; indirect communication context",
        },
        {
            "id": "PY-MAN-009",
            "kind": "type_alias",
            "ast_nodes": ["TypeAlias"],
            "landscape_role": "Typing only; no runtime signal",
        },
    ]


def _language_composites() -> list[dict[str, Any]]:
    """Derived language capabilities expressible as AST subgraphs."""
    return [
        {"id": "PY-LC-001", "name": "import_binding", "ast_nodes": ["Import", "ImportFrom"], "note": "Static import surface for library detection"},
        {"id": "PY-LC-002", "name": "call_site", "ast_nodes": ["Call"], "note": "Client/server invocation boundary"},
        {"id": "PY-LC-003", "name": "async_await", "ast_nodes": ["AsyncFunctionDef", "Await", "AsyncFor", "AsyncWith"], "note": "Concurrent I/O patterns"},
        {"id": "PY-LC-004", "name": "context_manager", "ast_nodes": ["With", "AsyncWith"], "note": "Connection/session scope (DB, HTTP)"},
        {"id": "PY-LC-005", "name": "decorator", "ast_nodes": ["FunctionDef", "AsyncFunctionDef", "ClassDef"], "fields": ["decorator_list"], "note": "Framework route/instrumentation hooks"},
        {"id": "PY-LC-006", "name": "exception_boundary", "ast_nodes": ["Try", "ExceptHandler", "Raise"], "note": "OTel exception recording (semconv exceptions)"},
        {"id": "PY-LC-007", "name": "generator", "ast_nodes": ["Yield", "YieldFrom"], "note": "Streaming/messaging pull patterns"},
        {"id": "PY-LC-008", "name": "pattern_match", "ast_nodes": ["Match", "match_case"], "note": "Structural dispatch (3.10+)"},
        {"id": "PY-LC-009", "name": "type_annotation", "ast_nodes": ["AnnAssign", "arg", "TypeAlias"], "note": "Static typing; no direct OTel span"},
        {"id": "PY-LC-010", "name": "comprehension", "ast_nodes": ["ListComp", "DictComp", "SetComp", "GeneratorExp"], "note": "Data shaping; internal"},
    ]


def _communication_crosswalk() -> list[dict[str, Any]]:
    """Map OTel landscape §5 patterns → Python AST/import/call detectors."""
    return [
        {
            "id": "PY-OTEL-5.1-HTTP",
            "landscape_ref": f"{LANDSCAPE_REF}#51-pattern-overview",
            "otel_pattern": "HTTP",
            "semconv_domain": "http",
            "span_kinds": ["CLIENT", "SERVER"],
            "import_signatures": [
                "urllib.request", "urllib3", "http.client", "httpx", "requests", "aiohttp",
                "fastapi", "starlette", "flask", "django.http", "uvicorn",
            ],
            "call_signatures": [".get(", ".post(", ".put(", ".delete(", ".request(", "urlopen("],
            "ast_nodes": ["Import", "ImportFrom", "Call", "FunctionDef", "AsyncFunctionDef"],
            "decorator_signatures": ["route", "get", "post", "api_view"],
        },
        {
            "id": "PY-OTEL-5.2-HTTP-METRICS",
            "landscape_ref": f"{LANDSCAPE_REF}#52-http",
            "otel_pattern": "HTTP metrics",
            "semconv_domain": "http",
            "metric_hints": ["http.server.duration", "http.client.duration"],
            "ast_nodes": ["Call"],
            "note": "Emitted by instrumentation, not intrinsic to AST",
        },
        {
            "id": "PY-OTEL-5.3-RPC",
            "landscape_ref": f"{LANDSCAPE_REF}#53-rpc-including-grpc",
            "otel_pattern": "RPC / gRPC",
            "semconv_domain": "rpc",
            "span_kinds": ["CLIENT", "SERVER"],
            "import_signatures": ["grpc", "grpc.aio", "google.protobuf"],
            "call_signatures": ["grpc.server", "insecure_channel", "secure_channel", "stub"],
            "ast_nodes": ["ClassDef", "FunctionDef", "AsyncFunctionDef", "Call"],
            "attribute_hints": ["rpc.system=grpc", "rpc.service", "rpc.method"],
        },
        {
            "id": "PY-OTEL-5.3-CONNECT",
            "landscape_ref": f"{LANDSCAPE_REF}#53-rpc-including-grpc",
            "otel_pattern": "Connect RPC",
            "semconv_domain": "rpc",
            "import_signatures": ["connectrpc", "connect-python"],
            "ast_nodes": ["Import", "ImportFrom", "Call"],
        },
        {
            "id": "PY-OTEL-5.4-MESSAGING",
            "landscape_ref": f"{LANDSCAPE_REF}#54-messaging-async--event-driven",
            "otel_pattern": "Messaging",
            "semconv_domain": "messaging",
            "span_kinds": ["PRODUCER", "CONSUMER"],
            "import_signatures": [
                "kafka", "aiokafka", "confluent_kafka", "pika", "celery", "redis",
                "boto3", "google.cloud.pubsub_v1", "azure.servicebus",
            ],
            "call_signatures": ["send(", "publish(", "produce(", "consume(", "basic_publish"],
            "ast_nodes": ["Call", "With", "AsyncWith", "FunctionDef", "AsyncFunctionDef"],
            "attribute_hints": ["messaging.system", "messaging.destination.name"],
        },
        {
            "id": "PY-OTEL-5.5-DATABASE",
            "landscape_ref": f"{LANDSCAPE_REF}#55-database-sync-data-access",
            "otel_pattern": "Database",
            "semconv_domain": "db",
            "span_kinds": ["CLIENT"],
            "import_signatures": [
                "sqlite3", "psycopg2", "psycopg", "asyncpg", "pymysql", "mysql.connector",
                "sqlalchemy", "django.db", "pymongo", "redis", "elasticsearch", "boto3.dynamodb",
            ],
            "call_signatures": ["execute(", "executemany(", "cursor(", "connect(", "from_url("],
            "ast_nodes": ["Call", "With", "AsyncWith"],
            "attribute_hints": ["db.system", "db.statement"],
        },
        {
            "id": "PY-OTEL-5.6-GRAPHQL",
            "landscape_ref": f"{LANDSCAPE_REF}#56-graphql-faas-feature-flags-genai",
            "otel_pattern": "GraphQL",
            "semconv_domain": "graphql",
            "import_signatures": ["graphene", "strawberry", "ariadne", "graphql"],
            "ast_nodes": ["FunctionDef", "AsyncFunctionDef", "ClassDef", "Call"],
        },
        {
            "id": "PY-OTEL-5.6-FAAS",
            "landscape_ref": f"{LANDSCAPE_REF}#56-graphql-faas-feature-flags-genai",
            "otel_pattern": "FaaS",
            "semconv_domain": "faas",
            "import_signatures": ["awslambdaric", "functions_framework"],
            "call_signatures": ["lambda_handler"],
            "ast_nodes": ["FunctionDef"],
        },
        {
            "id": "PY-OTEL-5.6-FEATURE-FLAGS",
            "landscape_ref": f"{LANDSCAPE_REF}#56-graphql-faas-feature-flags-genai",
            "otel_pattern": "Feature flags",
            "semconv_domain": "feature-flags",
            "import_signatures": ["openfeature", "flagd", "launchdarkly"],
            "call_signatures": ["get_boolean_value", "resolve_boolean_details"],
            "ast_nodes": ["Call"],
            "attribute_hints": ["feature_flag.key"],
        },
        {
            "id": "PY-OTEL-5.6-GENAI",
            "landscape_ref": f"{LANDSCAPE_REF}#56-graphql-faas-feature-flags-genai",
            "otel_pattern": "Generative AI",
            "semconv_domain": "gen-ai",
            "import_signatures": ["openai", "anthropic", "google.generativeai", "langchain"],
            "call_signatures": ["chat.completions.create", "messages.create"],
            "ast_nodes": ["Call", "Import", "ImportFrom"],
            "note": "GenAI semconv lives in external OTel repo",
        },
        {
            "id": "PY-OTEL-5.7-CICD",
            "landscape_ref": f"{LANDSCAPE_REF}#57-cicd-and-cli",
            "otel_pattern": "CI/CD",
            "semconv_domain": "cicd",
            "import_signatures": ["opentelemetry.instrumentation.cicd"],
            "ast_nodes": ["FunctionDef", "Call"],
        },
        {
            "id": "PY-OTEL-5.7-CLI",
            "landscape_ref": f"{LANDSCAPE_REF}#57-cicd-and-cli",
            "otel_pattern": "CLI",
            "semconv_domain": "cli",
            "import_signatures": ["click", "typer", "argparse"],
            "call_signatures": ["@click.command", "typer.run", "ArgumentParser.parse_args"],
            "ast_nodes": ["FunctionDef", "Call", "If"],
        },
        {
            "id": "PY-OTEL-5.1-DNS",
            "landscape_ref": f"{LANDSCAPE_REF}#51-pattern-overview",
            "otel_pattern": "DNS",
            "semconv_domain": "dns",
            "import_signatures": ["socket", "dns.resolver"],
            "call_signatures": ["getaddrinfo(", "resolve("],
            "ast_nodes": ["Call"],
        },
        {
            "id": "PY-OTEL-5.1-OBJECT-STORE",
            "landscape_ref": f"{LANDSCAPE_REF}#51-pattern-overview",
            "otel_pattern": "Object stores",
            "semconv_domain": "object-stores",
            "import_signatures": ["boto3", "google.cloud.storage", "azure.storage.blob"],
            "call_signatures": ["upload_file", "download_file", "put_object", "get_object"],
            "ast_nodes": ["Call"],
        },
        {
            "id": "PY-OTEL-5.1-CLOUD-SDK",
            "landscape_ref": f"{LANDSCAPE_REF}#51-pattern-overview",
            "otel_pattern": "Cloud provider SDKs",
            "semconv_domain": "cloud-providers",
            "import_signatures": ["boto3", "botocore", "google.cloud", "azure.identity"],
            "ast_nodes": ["Import", "ImportFrom", "Call"],
        },
    ]


def build_index() -> dict[str, Any]:
    ast_nodes = _build_ast_nodes()
    manifest = _manifest_kinds()
    composites = _language_composites()
    crosswalk = _communication_crosswalk()
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "python_version": sys.version.split()[0],
        "landscape_ref": LANDSCAPE_REF,
        "counts": {
            "ast_nodes": len(ast_nodes),
            "manifest_kinds": len(manifest),
            "language_composites": len(composites),
            "communication_patterns": len(crosswalk),
        },
        "ast_nodes": ast_nodes,
        "manifest_kinds": manifest,
        "language_composites": composites,
        "communication_crosswalk": crosswalk,
    }


def _serialize(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="Verify on-disk index matches generated")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)

    doc = build_index()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "index-meta.json": {
            k: doc[k]
            for k in (
                "schema_version", "generator", "python_version",
                "landscape_ref", "counts",
            )
        },
        "ast-nodes.json": {"schema_version": doc["schema_version"], "nodes": doc["ast_nodes"]},
        "manifest-kinds.json": {"schema_version": doc["schema_version"], "kinds": doc["manifest_kinds"]},
        "language-composites.json": {"schema_version": doc["schema_version"], "composites": doc["language_composites"]},
        "communication-crosswalk.json": {
            "schema_version": doc["schema_version"],
            "landscape_ref": doc["landscape_ref"],
            "patterns": doc["communication_crosswalk"],
        },
        "full-index.json": doc,
    }

    drift = False
    for name, payload in files.items():
        text = _serialize(payload)
        path = out_dir / name
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else None
            if current != text:
                print(f"DRIFT: {name}")
                drift = True
        else:
            path.write_text(text, encoding="utf-8")

    if args.check:
        if drift:
            print("Index OUT OF SYNC — run gen_python_ast_capability_index.py")
            return 1
        print(f"OK: index in sync ({doc['counts']})")
        return 0

    print(f"Wrote {len(files)} files to {out_dir}")
    print(f"  ast_nodes={doc['counts']['ast_nodes']}  crosswalk={doc['counts']['communication_patterns']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
