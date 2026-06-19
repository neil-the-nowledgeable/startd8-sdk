"""Unit tests for Python capability resolver (hyp(f) pass)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.python_capability_resolver import (
    analyze_corpus,
    analyze_file,
    extract_signals,
    load_index,
    match_patterns,
    report_to_dict,
)

_REPO = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_load_index_has_patterns() -> None:
    index = load_index()
    assert len(index["patterns"]) >= 10
    assert index["meta"]["schema_version"] == "1.0"


@pytest.mark.unit
def test_extract_signals_grpc_and_db() -> None:
    source = '''
import grpc
import psycopg2

def connect():
    return psycopg2.connect("dbname=test")

class Greeter(grpc.Servicer):
    def SayHello(self, request, context):
        pass
'''
    sig = extract_signals(source)
    assert "grpc" in sig.imports
    assert "psycopg2" in sig.imports
    assert "class" in sig.manifest_kinds
    assert "method" in sig.manifest_kinds


@pytest.mark.unit
def test_match_patterns_rpc_and_database() -> None:
    index = load_index()
    sig = extract_signals("import grpc\nimport psycopg2\npsycopg2.connect()\n")
    matches = match_patterns(sig, index["patterns"])
    ids = {m.pattern_id for m in matches}
    assert "PY-OTEL-5.3-RPC" in ids
    assert "PY-OTEL-5.5-DATABASE" in ids


@pytest.mark.unit
def test_match_patterns_flask_http() -> None:
    index = load_index()
    sig = extract_signals("from flask import Flask\napp = Flask(__name__)\n")
    matches = match_patterns(sig, index["patterns"])
    assert any(m.pattern_id == "PY-OTEL-5.1-HTTP" for m in matches)


@pytest.mark.unit
def test_analyze_file_skips_generated_pb2(tmp_path: Path) -> None:
    index = load_index()
    gen = tmp_path / "src" / "svc" / "demo_pb2.py"
    gen.parent.mkdir(parents=True)
    gen.write_text("# generated\n", encoding="utf-8")
    report = analyze_file(gen, workdir=tmp_path, patterns=index["patterns"])
    assert report.skipped_generated
    assert report.hyp == []


@pytest.mark.unit
def test_analyze_corpus_mini_fixture(tmp_path: Path) -> None:
    svc = tmp_path / "src" / "demo"
    svc.mkdir(parents=True)
    (svc / "server.py").write_text(
        "import openfeature\nfrom openfeature import api\n"
        "import grpc\n"
        "def handler():\n    api.get_client().get_boolean_value('flag', False)\n",
        encoding="utf-8",
    )
    (svc / "demo_pb2_grpc.py").write_text("# skip me\n", encoding="utf-8")

    report = analyze_corpus(tmp_path, corpus="test-fixture", skip_generated=True)
    assert report.files_analyzed == 1
    assert report.files_skipped_generated == 1
    assert "PY-OTEL-5.3-RPC" in report.pattern_union
    assert "PY-OTEL-5.6-FEATURE-FLAGS" in report.pattern_union
    assert report.overall_index_percent > 0

    doc = report_to_dict(report)
    assert doc["schema_version"] == "1.0"
    server = next(f for f in doc["files"] if f["rel_path"].endswith("server.py"))
    assert server["hyp"]


@pytest.mark.unit
def test_otel_demo_coverage_artifact_present() -> None:
    path = _REPO / "docs" / "design" / "python-capability-index" / "otel-demo-python-coverage.json"
    if not path.exists():
        pytest.skip("run scripts/analyze_otel_demo_python_coverage.py first")
    doc = json.loads(path.read_text())
    assert doc["corpus"] == "otel-demo-python+fixtures"
    assert doc["summary"]["overall_index_percent"] == 70.6
    assert len(doc["summary"]["pattern_union"]) == 7
