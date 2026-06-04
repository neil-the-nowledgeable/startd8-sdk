"""Rung-4 deterministic contract-test emitter (Python contract-codegen).

Proves the emitter is (1) byte-stable, (2) part of the assembled backend, (3) recognized + judged
in-sync by the shared drift/provider path ($0 skip), and — the point — (4) the tests it emits
actually RUN GREEN against the generated Pydantic models. Anchored on the real StartDate
ProofPoint+Metric pilot contract.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from startd8.backend_codegen import (
    CONTRACT_TESTS_PATH,
    render_backend,
    render_contract_tests,
    render_pydantic_models,
)
from startd8.backend_codegen.drift import check_drift, owned_file_in_sync

pytestmark = pytest.mark.unit

# The StartDate pilot bounded context: a relation/FK, an enum, a list, optionals.
PILOT_SCHEMA = """
enum Confidence {
  LOW
  MEDIUM
  HIGH
}

model ProofPoint {
  id         String     @id
  situation  String
  action     String
  result     String
  confidence Confidence
  tags       String[]
  metricId   String?
  metric     Metric?    @relation(fields: [metricId], references: [id])
}

model Metric {
  id      String  @id
  value   Float
  unit    String
  context String?
}
"""


def test_render_is_byte_identical_on_regen():
    a = render_contract_tests(PILOT_SCHEMA, "prisma/schema.prisma")
    b = render_contract_tests(PILOT_SCHEMA, "prisma/schema.prisma")
    assert a == b
    assert a.startswith("# GENERATED from prisma/schema.prisma")
    assert "# startd8-artifact: python-tests-contract" in a


def test_contract_tests_are_in_assembled_backend():
    paths = {rel for rel, _ in render_backend(PILOT_SCHEMA)}
    assert CONTRACT_TESTS_PATH in paths


def test_emitted_tests_cover_each_entity():
    text = render_contract_tests(PILOT_SCHEMA)
    # round-trip + field tests for both entities; enum-domain for the entity with the enum
    for fn in (
        "def test_proofpoint_roundtrip(",
        "def test_proofpoint_fields(",
        "def test_proofpoint_confidence_enum_domain(",
        "def test_metric_roundtrip(",
        "def test_metric_fields(",
    ):
        assert fn in text
    # FK scalar is asserted present-and-optional; the relation object is not a model field
    assert "'metricId' in f and not f['metricId'].is_required()" in text


def test_fresh_render_is_in_sync_dollar_zero():
    text = render_contract_tests(PILOT_SCHEMA, "prisma/schema.prisma")
    # The skip-hook predicate: owned + verifiably in-sync against the schema.
    assert owned_file_in_sync(PILOT_SCHEMA, text) is True
    assert check_drift(PILOT_SCHEMA, text, source_file="prisma/schema.prisma").status == "in_sync"


def test_drift_detects_tamper():
    text = render_contract_tests(PILOT_SCHEMA, "prisma/schema.prisma")
    tampered = text.replace('"sample"', '"hand-edited"', 1)
    assert owned_file_in_sync(PILOT_SCHEMA, tampered) is False


def test_emitted_tests_run_green_against_generated_app(tmp_path):
    """The rung-4 gate: write the generated models + the emitted tests, run pytest, expect green."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "models.py").write_text(
        render_pydantic_models(PILOT_SCHEMA, source_file="prisma/schema.prisma").text,
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_contract.py").write_text(
        render_contract_tests(PILOT_SCHEMA, "prisma/schema.prisma"), encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_contract.py", "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"emitted tests failed:\n{result.stdout}\n{result.stderr}"
    assert "5 passed" in result.stdout
