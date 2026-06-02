"""Inc 8 — `startd8 generate frontend` CLI (FR-8A, FR-11 exit-code contract)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from startd8.cli_generate import generate_app

pytestmark = pytest.mark.unit

runner = CliRunner()

SCHEMA = "model M {\n  id String @id\n  name String\n}\n"
SCHEMA_V2 = "model M {\n  id String @id\n  name String\n  extra String?\n}\n"


def _schema_file(tmp_path, text=SCHEMA):
    p = tmp_path / "schema.prisma"
    p.write_text(text, encoding="utf-8")
    return p


def test_generate_writes_file(tmp_path):
    schema = _schema_file(tmp_path)
    out = tmp_path / "lib" / "value-model.ts"
    result = runner.invoke(
        generate_app, ["frontend", "--schema", str(schema), "--out", str(out)]
    )
    assert result.exit_code == 0
    assert out.exists()
    text = out.read_text()
    assert "// GENERATED from" in text
    assert "export const MSchema = z.object({" in text


def test_check_in_sync_exits_zero(tmp_path):
    schema = _schema_file(tmp_path)
    out = tmp_path / "value-model.ts"
    assert (
        runner.invoke(
            generate_app, ["frontend", "--schema", str(schema), "--out", str(out)]
        ).exit_code
        == 0
    )
    result = runner.invoke(
        generate_app,
        ["frontend", "--schema", str(schema), "--out", str(out), "--check"],
    )
    assert result.exit_code == 0
    assert "in_sync" in result.stdout


def test_check_stale_exits_one(tmp_path):
    schema = _schema_file(tmp_path)
    out = tmp_path / "value-model.ts"
    runner.invoke(
        generate_app, ["frontend", "--schema", str(schema), "--out", str(out)]
    )
    # Schema changes; the on-disk file is now stale.
    schema.write_text(SCHEMA_V2, encoding="utf-8")
    result = runner.invoke(
        generate_app,
        ["frontend", "--schema", str(schema), "--out", str(out), "--check"],
    )
    assert result.exit_code == 1
    assert "stale" in result.stdout


def test_check_missing_exits_one(tmp_path):
    schema = _schema_file(tmp_path)
    out = tmp_path / "nope.ts"
    result = runner.invoke(
        generate_app,
        ["frontend", "--schema", str(schema), "--out", str(out), "--check"],
    )
    assert result.exit_code == 1
    assert "missing" in result.stdout


def test_unreadable_schema_exits_two(tmp_path):
    out = tmp_path / "value-model.ts"
    result = runner.invoke(
        generate_app,
        ["frontend", "--schema", str(tmp_path / "absent.prisma"), "--out", str(out)],
    )
    assert result.exit_code == 2


def test_strict_with_unrenderable_exits_two(tmp_path):
    schema = _schema_file(
        tmp_path, "model M {\n  id String @id\n  geom Unsupported\n}\n"
    )
    out = tmp_path / "value-model.ts"
    result = runner.invoke(
        generate_app,
        ["frontend", "--schema", str(schema), "--out", str(out), "--strict"],
    )
    assert result.exit_code == 2
    assert "unrenderable" in result.stdout
