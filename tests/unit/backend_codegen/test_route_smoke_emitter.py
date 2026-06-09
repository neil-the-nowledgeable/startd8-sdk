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

    def test_reset_has_fail_loud_nontemp_guard(self):
        """F-12 belt-and-suspenders: on top of the dedicated temp engine, _reset() refuses to
        DELETE unless the engine resolves to a temp path — fail-loud (skip) rather than wipe a
        real DB if a future change ever re-points _engine. STARTD8_ALLOW_NONTEMP_RESET opts out."""
        text = render_route_smoke_tests(PILOT)
        assert "def _engine_is_temp()" in text
        assert "STARTD8_ALLOW_NONTEMP_RESET" in text
        # the guard is the FIRST thing _reset does, before any delete()
        reset_body = text.split("def _reset(session):")[1].split("def ")[0]
        assert reset_body.index("_engine_is_temp()") < reset_body.index("delete(")
        assert "refuses to DELETE" in reset_body
        # exec the guard logic: a temp-dir sqlite url passes, ./app.db is refused
        import tempfile
        from pathlib import Path as _P
        tmp = _P(tempfile.gettempdir()).resolve()
        for url, want in [(f"sqlite:///{tmp/'x'/'smoke.db'}", True),
                          ("sqlite:///./app.db", False),
                          ("postgresql://h/db", False)]:
            ok = url.startswith("sqlite:///") and (
                lambda p: tmp in p.parents or p == tmp
            )(_P(url[len("sqlite:///"):]).resolve()) if url.startswith("sqlite:///") else False
            assert ok is want, (url, ok)


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

    def test_route_smoke_never_wipes_the_real_db(self, tmp_path):
        """F-12: running the suite must NOT touch the operator's real app.db, even when
        app.db is imported/bound first. Pre-seed the real ./app.db with a sentinel row,
        run the full suite, and assert the row survives (the regression that emptied a
        real 116-row model on a regen's pytest run)."""
        pytest.importorskip("fastapi")
        pytest.importorskip("sqlmodel")
        pytest.importorskip("jinja2")
        pytest.importorskip("multipart")
        pytest.importorskip("httpx")
        pytest.importorskip("yaml")

        self._generate(tmp_path)
        # Seed the REAL app.db (sqlite:///./app.db, relative to cwd) with a sentinel,
        # then run the route-smoke suite, then re-read — all in one subprocess so the
        # real engine is bound (the exact condition that no-op'd the old guard).
        driver = (
            "import sys; sys.path.insert(0, '.')\n"
            "from sqlmodel import Session, select\n"
            "from app.db import engine, init_db\n"
            "from app import tables as t\n"
            "init_db()\n"
            "with Session(engine) as s:\n"
            "    s.add(t.ProofPoint(id='keepme', title='real user data')); s.commit()\n"
            "import pytest\n"
            "rc = pytest.main(['tests/test_route_smoke.py', '-q'])\n"
            "with Session(engine) as s:\n"
            "    survived = s.get(t.ProofPoint, 'keepme') is not None\n"
            "print('SENTINEL_SURVIVED' if survived else 'SENTINEL_WIPED')\n"
        )
        (tmp_path / "_f12_driver.py").write_text(driver)
        proc = subprocess.run(
            [sys.executable, "_f12_driver.py"],
            cwd=tmp_path, capture_output=True, text=True, timeout=300,
        )
        assert "SENTINEL_SURVIVED" in proc.stdout, (
            f"route-smoke wiped the real app.db!\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
        assert "SENTINEL_WIPED" not in proc.stdout

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
