"""M6 CLI tests (FR-10) — `startd8 promote tsdb <metric>` orchestration via CliRunner.

Uses a recorded --specimen file (the primary path; gov series are retention-pruned) so the whole
M0→M5 pipeline is exercised without a live TSDB.
"""

from __future__ import annotations

from itertools import product

import pytest
from typer.testing import CliRunner

from startd8.cli_tsdb import promote_app
from startd8.tsdb_maturation import (
    ReadResult,
    Series,
    Specimen,
    write_specimen,
)

runner = CliRunner()
METRIC = "gov_expenditure_amount"
ENTITY = "DepartmentBudget"


@pytest.fixture
def specimen_file(tmp_path):
    series, v = [], 1_000_000.0
    for dept, fy, status, fund in product(
        ["corrections", "health"], ["2025", "2026"], ["enacted", "proposed"], ["general", "federal"]
    ):
        labels = {"department": dept, "fiscal_year": fy, "budget_status": status,
                  "fund_source": fund, "source": "hfa_mi"}
        series.append(Series(labels=labels, value=round(v, 2), timestamp=1_700_000_000.0))
        v += 1000.0
    spec = Specimen.from_read_result(ReadResult(metric=METRIC, lookback="3000d", series=tuple(series)))
    path = tmp_path / "specimen.json"
    write_specimen(spec, path)
    return path


def _run(args):
    return runner.invoke(promote_app, args)


# --------------------------------------------------------------------------- #
# Input validation.                                                            #
# --------------------------------------------------------------------------- #
def test_requires_specimen_or_endpoint():
    result = _run(["tsdb", METRIC])
    assert result.exit_code == 2  # BadParameter


def test_reduce_flag_is_not_yet_implemented(specimen_file):
    result = _run(["tsdb", METRIC, "--specimen", str(specimen_file), "--reduce", "top-10"])
    assert result.exit_code == 2
    assert "not yet implemented" in result.stdout


# --------------------------------------------------------------------------- #
# --dry-run: read → infer → surface, writes nothing.                           #
# --------------------------------------------------------------------------- #
def test_dry_run_shows_surface_and_writes_nothing(specimen_file, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    result = _run(["tsdb", METRIC, "--specimen", str(specimen_file), "--entity", ENTITY,
                   "--project", str(project), "--dry-run"])
    assert result.exit_code == 0
    assert "inferred key" in result.stdout
    assert "records:   16" in result.stdout
    assert not (project / "prisma" / "schema.prisma").exists()
    assert not (project / "imports.yaml").exists()


# --------------------------------------------------------------------------- #
# Promotion refused without confirmation, allowed after --confirm.             #
# --------------------------------------------------------------------------- #
def test_promote_refused_without_confirmation(specimen_file, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    result = _run(["tsdb", METRIC, "--specimen", str(specimen_file), "--entity", ENTITY,
                   "--project", str(project), "--no-generate-app"])
    assert result.exit_code == 1
    assert "refused" in result.stdout
    assert "confirmation required" in result.stdout


def test_confirm_records_marker(specimen_file, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    result = _run(["tsdb", METRIC, "--specimen", str(specimen_file), "--entity", ENTITY,
                   "--project", str(project), "--confirm"])
    assert result.exit_code == 0
    assert "confirmed" in result.stdout
    assert (project / "docs" / "tsdb-maturation" / "confirmed.yaml").is_file()


def test_confirm_then_promote_flips_schema_and_writes_manifests(specimen_file, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    # 1. confirm
    assert _run(["tsdb", METRIC, "--specimen", str(specimen_file), "--entity", ENTITY,
                 "--project", str(project), "--confirm"]).exit_code == 0
    # 2. promote (no app render to keep it light)
    result = _run(["tsdb", METRIC, "--specimen", str(specimen_file), "--entity", ENTITY,
                   "--project", str(project), "--no-generate-app"])
    assert result.exit_code == 0, result.stdout
    assert "promoted" in result.stdout
    assert (project / "prisma" / "schema.prisma").is_file()
    assert (project / "imports.yaml").is_file()
    assert (project / f"backfill-{ENTITY}.json").is_file()
    # the promoted schema carries the composite identity
    schema = (project / "prisma" / "schema.prisma").read_text()
    assert "model DepartmentBudget" in schema
    assert "@@unique" in schema


# --------------------------------------------------------------------------- #
# --force bypasses the confirmation gate.                                       #
# --------------------------------------------------------------------------- #
def test_force_bypasses_confirmation(specimen_file, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    result = _run(["tsdb", METRIC, "--specimen", str(specimen_file), "--entity", ENTITY,
                   "--project", str(project), "--force", "--no-generate-app"])
    assert result.exit_code == 0
    assert "promoted" in result.stdout


# --------------------------------------------------------------------------- #
# --generate-app renders the backend.                                          #
# --------------------------------------------------------------------------- #
def test_generate_app_renders_backend(specimen_file, tmp_path):
    pytest.importorskip("sqlmodel")
    from startd8.tsdb_maturation import confirm_inference, infer_schema, load_specimen

    project = tmp_path / "proj"
    project.mkdir()
    # Confirm the inferred key (emitted field names) via the tool so it matches exactly.
    res = infer_schema(load_specimen(specimen_file), entity_name=ENTITY)
    confirm_inference(project, res, METRIC, today="2026-07-08")

    result = _run(["tsdb", METRIC, "--specimen", str(specimen_file), "--entity", ENTITY,
                   "--project", str(project)])
    assert result.exit_code == 0, result.stdout
    assert "generated" in result.stdout
    assert (project / "app" / "tables.py").is_file()
    assert (project / "app" / "importer.py").is_file()
