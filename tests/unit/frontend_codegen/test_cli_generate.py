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


# ---------------------------------------------------------------------------
# Surface 3 / MODEL_CONFIG — `generate backend --ai-agent-spec`
# ---------------------------------------------------------------------------

from tests.unit.backend_codegen.test_ai_layer import (  # noqa: E402
    SCHEMA as AI_SCHEMA,
    MANIFEST as AI_MANIFEST,
    HUMAN as AI_HUMAN,
)


def _ai_fixtures(tmp_path):
    s = tmp_path / "schema.prisma"; s.write_text(AI_SCHEMA, encoding="utf-8")
    m = tmp_path / "ai_passes.yaml"; m.write_text(AI_MANIFEST, encoding="utf-8")
    h = tmp_path / "human.yaml"; h.write_text(AI_HUMAN, encoding="utf-8")
    return s, m, h


def test_backend_ai_agent_spec_baked(tmp_path):
    s, m, h = _ai_fixtures(tmp_path)
    out = tmp_path / "out"
    result = runner.invoke(generate_app, [
        "backend", "--schema", str(s), "--ai-passes", str(m), "--human-inputs", str(h),
        "--ai-agent-spec", "gemini:gemini-2.5-pro",
        "--source-label", "schema.prisma", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    svc = (out / "app" / "ai" / "service.py").read_text()
    assert 'DEFAULT_AGENT_SPEC = "gemini:gemini-2.5-pro"' in svc
    assert "# ai-agent-spec: gemini:gemini-2.5-pro" in svc


def test_backend_custom_spec_check_in_sync_without_flag(tmp_path):
    """A custom-spec backend re-checks in_sync without re-passing --ai-agent-spec
    (the generated service.py self-describes its spec — the drift-hash fix)."""
    s, m, h = _ai_fixtures(tmp_path)
    out = tmp_path / "out"
    assert runner.invoke(generate_app, [
        "backend", "--schema", str(s), "--ai-passes", str(m), "--human-inputs", str(h),
        "--ai-agent-spec", "gemini:gemini-2.5-pro",
        "--source-label", "schema.prisma", "--out", str(out),
    ]).exit_code == 0
    result = runner.invoke(generate_app, [
        "backend", "--schema", str(s), "--ai-passes", str(m), "--human-inputs", str(h),
        "--source-label", "schema.prisma", "--out", str(out), "--check",
    ])
    assert result.exit_code == 0, result.output


def test_backend_ai_agent_spec_without_passes_warns(tmp_path):
    s = tmp_path / "schema.prisma"; s.write_text(AI_SCHEMA, encoding="utf-8")
    out = tmp_path / "out"
    result = runner.invoke(generate_app, [
        "backend", "--schema", str(s), "--ai-agent-spec", "gemini:gemini-2.5-pro",
        "--source-label", "schema.prisma", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert "ignored without --ai-passes" in result.output
