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
from startd8.backend_codegen.ai_layer import render_ai_pass_tests, render_edge_tests
from startd8.backend_codegen.drift import check_drift

pytestmark = pytest.mark.unit

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
    # contract(6) + completeness(2) + edge(3) + gate(2) = 13
    assert "16 passed" in result.stdout
