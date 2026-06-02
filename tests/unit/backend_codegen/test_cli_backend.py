"""Step 7 (FR-13) `startd8 generate backend` + Step 8 (FR-12) the ProofPoint+Metric pilot.

The pilot is the path's acceptance milestone: author the .prisma → generate the full backend →
re-check reports in-sync ($0.00 skip on regen) → the Python build gate is green.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from startd8.cli_generate import generate_app

pytestmark = pytest.mark.unit

runner = CliRunner()

# The locked pilot bounded context.
PILOT = """\
enum Confidence {
  draft
  confirmed
}

model ProofPoint {
  id         String     @id
  situation  String
  action     String
  result     String
  confidence Confidence
  tags       String[]
  metricId   String?
}

model Metric {
  id      String @id
  value   Float
  unit    String
  context String?
}
"""

EXPECTED_FILES = [
    "app/__init__.py",
    "app/models.py",
    "app/tables.py",
    "app/routers.py",
    "app/db.py",
    "app/main.py",
    "app/web.py",
    "app/export.py",
    "app/ai_schemas.py",
    "app/completeness.py",
    "app/templates/base.html",
    "app/templates/_field_error.html",
    "app/templates/proofpoint/list.html",
    "app/templates/proofpoint/form.html",
    "app/templates/metric/detail.html",
    "requirements.txt",
]


def _schema(tmp_path):
    p = tmp_path / "prisma" / "schema.prisma"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(PILOT, encoding="utf-8")
    return p


def test_generate_backend_writes_full_spine(tmp_path):
    schema = _schema(tmp_path)
    result = runner.invoke(
        generate_app, ["backend", "--schema", str(schema), "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    for rel in EXPECTED_FILES:
        assert (tmp_path / rel).exists(), f"missing {rel}"
    # spot-check the cross-layer projection landed coherently
    assert (
        "class ProofPointSchema(BaseModel):" in (tmp_path / "app/models.py").read_text()
    )
    assert (
        "class ProofPoint(SQLModel, table=True):"
        in (tmp_path / "app/tables.py").read_text()
    )
    assert 'prefix="/proofpoint"' in (tmp_path / "app/routers.py").read_text()


def test_check_before_generate_reports_drift(tmp_path):
    schema = _schema(tmp_path)
    # nothing written yet -> --check must report drift (missing) and exit 1
    result = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--check"],
    )
    assert result.exit_code == 1


def test_pilot_regen_is_zero_cost_and_gate_green(tmp_path):
    """FR-12 acceptance: generate → re-check in-sync ($0.00 regen) → build gate green."""
    schema = _schema(tmp_path)
    gen = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--gate"],
    )
    assert gen.exit_code == 0, gen.output
    assert "build gate: pass" in gen.output

    # re-check: every owned artifact is recognized in-sync -> the skip-hook would mark it $0.00
    chk = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--check"],
    )
    assert chk.exit_code == 0, chk.output
    assert "in_sync" in chk.output


def test_check_detects_handedit(tmp_path):
    schema = _schema(tmp_path)
    runner.invoke(
        generate_app, ["backend", "--schema", str(schema), "--out", str(tmp_path)]
    )
    # tamper an owned file -> --check exits 1
    models = tmp_path / "app" / "models.py"
    models.write_text(
        models.read_text().replace("situation: str", "situation: int"), encoding="utf-8"
    )
    chk = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--check"],
    )
    assert chk.exit_code == 1
