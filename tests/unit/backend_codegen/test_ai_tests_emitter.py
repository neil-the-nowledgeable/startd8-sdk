"""Rung-4 AI-layer semantic tests (Iterations 2b + 3).

Proves the two AI-layer test emitters: FR-6/NFR-2 edge privacy (the AI tool-input omits human-authored
+ server-managed fields) and the offline provenance gate (an AI-persisted row is source="ai",
confirmed=False — and a Metric persists with no AI-authored value). Both are three-input artifacts
(schema + ai_passes + human_inputs), drift-checked via the three-hash path.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from startd8.backend_codegen import render_backend
from startd8.backend_codegen.ai_layer import (
    render_ai_pass_tests,
    render_edge_tests,
    render_server,
)
from startd8.backend_codegen.crud_generator import render_main
from startd8.backend_codegen.drift import check_drift
from startd8.backend_codegen.test_emitter import render_route_smoke_tests

pytestmark = pytest.mark.unit


def test_f9_main_mounts_ai_router_tolerantly():
    """F-9: main.py mounts ai_router via a tolerant optional import — reachable at /ai/* when the
    AI layer was generated, a no-op (schema-only, byte-identical) when it wasn't."""
    schema = "model ProofPoint {\n  id String @id\n  title String\n}\n"
    m = render_main(schema)
    assert "from .ai.routes import ai_router" in m
    assert "except ModuleNotFoundError" in m
    assert "app.include_router(ai_router)" in m
    # static block, no manifest input -> byte-identical regardless of --ai-passes
    assert render_main(schema) == render_main(schema)


def test_f9_server_does_not_double_mount_ai_router():
    """F-9: server.py re-exports main's (already AI-mounted) app — mounting ai_router there too
    would duplicate every /ai/* route. It must NOT include_router(ai_router)."""
    srv = render_server("model P {\n  id String @id\n}\n", "passes: []", None)
    assert "from app.main import app" in srv
    assert "include_router(ai_router)" not in srv


def test_f9_route_smoke_post_smokes_ai_routes():
    """F-9(b): the generated route-smoke POST-smokes /ai/* (non-404) so an unmounted AI layer
    fails loud — GET-smoke alone cannot catch a missing POST layer."""
    rs = render_route_smoke_tests("model P {\n  id String @id\n}\n")
    assert "def test_ai_routes_mounted_if_ai_layer_present" in rs
    assert 'r.path.startswith("/ai/")' in rs
    assert "!= 404" in rs
    assert "raise_server_exceptions=False" in rs  # a 500 still proves mounted

# Two passes: extract → ProofPoint (text), quantify → Metric. Metric.value is human-authored, so the
# AI edge for Metric must omit it (FR-6); value is optional so an AI-persisted Metric is still valid.
SCHEMA = """
model ProofPoint {
  id          String  @id @default(cuid())
  ownerId     String  @default("local")
  source      String  @default("user")
  confirmed   Boolean @default(true)
  title       String?
  description String?
}

model Metric {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  value     Float?
  unit      String?
}

model AiCall {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  purpose   String?
}
""".strip()

MANIFEST = """
passes:
  - name: extract
    output_entities: [ProofPoint]
    route_path: /extract
    prompt: prompts/extract.md
  - name: quantify
    output_entities: [Metric]
    route_path: /quantify
    prompt: prompts/quantify.md
""".strip()

HUMAN = """
fields:
  - target: Metric.value
    authored_by: human
""".strip()


def _backend():
    return {rel: text for rel, text in render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=HUMAN)}


def test_edge_and_pass_tests_are_in_backend():
    paths = _backend()
    assert "tests/test_edge_privacy.py" in paths
    assert "tests/test_ai_passes.py" in paths


def test_edge_tests_byte_identical_and_assert_fr6():
    a = render_edge_tests(SCHEMA, MANIFEST, HUMAN)
    assert a == render_edge_tests(SCHEMA, MANIFEST, HUMAN)
    # FR-6: the AI literally has no Metric.value field; NFR-2: the edge field set is exactly declared.
    assert "'value' not in MetricEdge.model_fields" in a
    assert 'set(MetricEdge.model_fields) == {"unit"}' in a


def test_pass_gate_tests_byte_identical_and_assert_provenance():
    a = render_ai_pass_tests(SCHEMA, MANIFEST, HUMAN)
    assert a == render_ai_pass_tests(SCHEMA, MANIFEST, HUMAN)
    assert "def test_quantify_metric_persist_is_ai_owned(" in a
    assert 'rows[0].source == "ai"' in a
    assert "rows[0].confirmed is False" in a


def test_ai_test_files_drift_in_sync_three_hash():
    # AI-layer artifacts verify against all three inputs (schema + ai_passes + human_inputs).
    edge = render_edge_tests(SCHEMA, MANIFEST, HUMAN, "prisma/schema.prisma")
    gate = render_ai_pass_tests(SCHEMA, MANIFEST, HUMAN, "prisma/schema.prisma")
    for text in (edge, gate):
        res = check_drift(
            SCHEMA, text, source_file="prisma/schema.prisma",
            manifest_text=MANIFEST, human_inputs_text=HUMAN,
        )
        assert res.status == "in_sync", res.detail


def test_emitted_ai_tests_run_green(tmp_path):
    """The gate the generated app runs: edge-privacy (pydantic) + provenance (sqlmodel)."""
    pytest.importorskip("sqlmodel")
    pytest.importorskip("fastapi")
    for rel, text in _backend().items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"emitted tests failed:\n{result.stdout}\n{result.stderr}"
    # contract + completeness + edge + gate + route-smoke (1 unseeded GET case — F-8)
    # + confirm-route existence (FR-CA-8) + /ai POST-smoke (F-9: AI routes now mounted)
    # + health readiness/liveness (2 — the generated tests/test_health.py)
    assert "21 passed" in result.stdout


# --------------------------------------------------------------------------- #
# FR-SBE-6: a source-bound pass's generated gate test must call `_persist_source`
# (the helper the bound harness actually defines) and assert the server-stamp —
# NOT `_persist` (which a bound harness does not emit). The `extract` pass below
# is bound by DERIVATION (no `source_binding:` key): ProofPoint carries a
# server-managed loose-reference `sourceDocumentId`.
# --------------------------------------------------------------------------- #

SCHEMA_BOUND = """
model ImportedDocument {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  label     String?
}

model ProofPoint {
  id               String  @id @default(cuid())
  ownerId          String  @default("local")
  source           String  @default("user")
  confirmed        Boolean @default(true)
  title            String?
  sourceDocumentId String?
}

model AiCall {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  purpose   String?
}
""".strip()

MANIFEST_BOUND = """
passes:
  - name: extract
    output_entities: [ProofPoint]
    route_path: /extract
    prompt: prompts/extract.md
""".strip()

HUMAN_BOUND = """
fields:
  - target: ProofPoint.sourceDocumentId
    authored_by: human
""".strip()


def test_bound_pass_gate_test_uses_persist_source_and_asserts_stamp():
    a = render_ai_pass_tests(SCHEMA_BOUND, MANIFEST_BOUND, HUMAN_BOUND)
    assert a == render_ai_pass_tests(SCHEMA_BOUND, MANIFEST_BOUND, HUMAN_BOUND)  # byte-stable
    assert "def test_extract_proof_point_persist_is_ai_owned_and_stamped(" in a
    assert "_persist_source(" in a
    assert 'rows[0].sourceDocumentId == "doc-x"' in a
    assert "mod._persist(" not in a  # the bound harness defines _persist_source, not _persist


def test_emitted_bound_ai_tests_run_green(tmp_path):
    """FR-SBE-6 acceptance: a generated app with a DERIVED source-bound pass has green generated
    tests. Pre-fix this failed — the gate test called `mod._persist` on a `_persist_source`-only
    harness (AttributeError)."""
    pytest.importorskip("sqlmodel")
    pytest.importorskip("fastapi")
    backend = {rel: text for rel, text in render_backend(
        SCHEMA_BOUND, manifest_text=MANIFEST_BOUND, human_inputs_text=HUMAN_BOUND)}
    for rel, text in backend.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"emitted bound tests failed:\n{result.stdout}\n{result.stderr}"
