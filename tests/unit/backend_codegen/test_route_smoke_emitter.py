"""Route-smoke suite emitter tests (strtd8 §8 F-8 — the rung-5 floor).

Render-level tests are dependency-free. The end-to-end test generates a real app
into tmp, seeds a fixture, and runs the GENERATED suite via subprocess pytest —
it skips cleanly when the generated app's runtime deps are absent (same posture
as test_runtime_smoke.py).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from startd8.backend_codegen.assembler import render_backend
from startd8.backend_codegen.drift import check_drift
from startd8.backend_codegen.test_emitter import (
    ROUTE_SMOKE_TESTS_PATH,
    render_route_smoke_tests,
)

pytestmark = pytest.mark.unit

PILOT = """\
model ProofPoint {
  id         String  @id
  title      String
  metricId   String?
  metric     Metric? @relation(fields: [metricId], references: [id])
}

model Metric {
  id    String @id
  value Float
}
"""


class TestRenderRouteSmoke:
    def test_byte_stable_and_parses(self):
        a = render_route_smoke_tests(PILOT)
        b = render_route_smoke_tests(PILOT)
        assert a == b
        ast.parse(a)  # the emitted module is valid Python

    def test_header_and_kind(self):
        text = render_route_smoke_tests(PILOT)
        assert text.startswith("# GENERATED from prisma/schema.prisma")
        assert "# startd8-artifact: python-tests-routes" in text
        assert "# schema-sha256:" in text

    def test_baked_maps_match_contract(self):
        text = render_route_smoke_tests(PILOT)
        assert '_TABLES = ["ProofPoint", "Metric"]' in text
        assert '"ProofPoint": ("id", "str")' in text
        assert '"Metric": ("id", "str")' in text

    def test_int_pk_baked_as_int(self):
        schema = "model Item {\n  id  Int @id\n  n   Int\n}\n"
        text = render_route_smoke_tests(schema)
        assert '"Item": ("id", "int")' in text

    def test_compound_pk_entity_in_tables_not_pk_map(self):
        schema = (
            "model Side {\n  id String @id\n}\n\n"
            "model Join {\n  aId String\n  bId String\n\n  @@id([aId, bId])\n}\n"
        )
        text = render_route_smoke_tests(schema)
        assert '"Join"' in text.split("_PK =")[0]  # reset/seed surface includes it
        assert '"Join":' not in text.split("_PK =")[1].split("\n")[0]  # no fill entry

    def test_assembled_and_drift_in_sync(self):
        artifacts = dict(render_backend(PILOT))
        assert ROUTE_SMOKE_TESTS_PATH in artifacts
        report = check_drift(PILOT, artifacts[ROUTE_SMOKE_TESTS_PATH])
        assert report.status == "in_sync", report

    def test_requirements_carry_httpx(self):
        artifacts = dict(render_backend(PILOT))
        assert "httpx" in artifacts["requirements.txt"]


class TestGeneratedSuiteRuns:
    """End-to-end: the generated suite passes against the generated app."""

    def _generate(self, tmp_path: Path) -> None:
        for rel, content in render_backend(PILOT):
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        # Empty user (sam-style): empty states must render
        (seeds / "test-user-empty.yaml").write_text("user: empty\nrows: {}\n")
        # Populated user (jo-style): rows without pks — the loader synthesizes
        (seeds / "test-user-full.yaml").write_text(
            "user: full\n"
            "rows:\n"
            "  Metric:\n"
            "  - value: 42.0\n"
            "  ProofPoint:\n"
            "  - title: Migrated 14 pipelines\n"
        )

    def test_generated_route_smoke_passes(self, tmp_path):
        pytest.importorskip("fastapi")
        pytest.importorskip("sqlmodel")
        pytest.importorskip("jinja2")
        pytest.importorskip("multipart")
        pytest.importorskip("httpx")
        pytest.importorskip("yaml")

        self._generate(tmp_path)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(tmp_path / ROUTE_SMOKE_TESTS_PATH), "-v"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        # Both fixtures exercised + the unseeded base case
        assert "unseeded" in proc.stdout
        assert "test-user-empty" in proc.stdout
        assert "test-user-full" in proc.stdout

    def test_generated_suite_catches_bad_route(self, tmp_path):
        """A user router that 500s must FAIL the generated suite (the F-8 point)."""
        pytest.importorskip("fastapi")
        pytest.importorskip("sqlmodel")
        pytest.importorskip("jinja2")
        pytest.importorskip("multipart")
        pytest.importorskip("httpx")
        pytest.importorskip("yaml")

        self._generate(tmp_path)
        # Mount a broken view through the regen-safe user_routers seam —
        # exactly where the strtd8 value-map 422 lived.
        (tmp_path / "app" / "user_routers.py").write_text(
            "from fastapi import APIRouter\n\n"
            "broken = APIRouter()\n\n\n"
            '@broken.get("/value-map")\n'
            "def value_map():\n"
            '    raise RuntimeError("unrenderable view")\n\n\n'
            "user_routers = [broken]\n"
        )
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(tmp_path / ROUTE_SMOKE_TESTS_PATH), "-x", "-q"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode != 0
        assert "/value-map" in proc.stdout
