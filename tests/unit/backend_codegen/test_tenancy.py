"""Tier B / M3 — tenant declaration validation + entity selection (B1, FR-TEN-2).

scoped_entities picks the models that already carry the owner FK (no synthesis); validate_tenant
rejects a declaration whose model/owner_field don't exist in the schema; the CLI enforces it and the
coherence auth-without-tenant WARN disappears once tenancy is declared.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from startd8.backend_codegen.tenancy import scoped_entities, validate_tenant
from startd8.cli_generate import generate_app
from startd8.scaffold_codegen import parse_app_manifest
from startd8.scaffold_codegen.coherence import evaluate_coherence

pytestmark = pytest.mark.unit

runner = CliRunner()

SCHEMA = """\
model User {
  id String @id
}

model Note {
  id      String @id
  text    String
  ownerId String
}

model Lookup {
  id    String @id
  label String
}
"""

DEPLOYED_TENANT = (
    "deployment:\n  mode: deployed\n  tenant:\n    model: User\n    owner_field: ownerId\n"
    "persistence:\n  path: postgresql://db/app\n"
    "deploy:\n  trust_gateway: true\n"  # ack a verifying gateway → clears the FR-CND-6 fail-closed ERROR
)


def test_scoped_entities_picks_only_owner_fk_holders():
    assert scoped_entities(SCHEMA, "ownerId") == ["Note"]  # User/Lookup lack the owner field
    assert scoped_entities(SCHEMA, "nope") == []


def test_validate_tenant_ok():
    assert validate_tenant(SCHEMA, "User", "ownerId") == []


def test_validate_tenant_unknown_model():
    issues = validate_tenant(SCHEMA, "Ghost", "ownerId")
    assert any("is not a model" in i for i in issues)


def test_validate_tenant_owner_field_scopes_nothing():
    issues = validate_tenant(SCHEMA, "User", "missing_field")
    assert any("scope nothing" in i for i in issues)


def test_coherence_warn_clears_when_tenant_declared():
    m = parse_app_manifest(DEPLOYED_TENANT)
    findings = evaluate_coherence(m, has_auth_seam=True, has_tenant=m.has_tenant)
    assert not any(f.code == "deployed-auth-no-tenant" for f in findings)  # tenancy retires the WARN


# --- CLI enforces tenant validation --------------------------------------------------------------

def _schema_file(tmp_path):
    p = tmp_path / "schema.prisma"
    p.write_text(SCHEMA, encoding="utf-8")
    return p


def test_cli_valid_tenant_builds_without_auth_warn(tmp_path):
    schema = _schema_file(tmp_path)
    manifest = tmp_path / "app.yaml"
    manifest.write_text(DEPLOYED_TENANT, encoding="utf-8")
    res = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--app-manifest", str(manifest)],
    )
    assert res.exit_code == 0, res.output
    assert "deployed-auth-no-tenant" not in res.output  # WARN retired by the tenant declaration


def test_cli_invalid_tenant_model_blocks_build(tmp_path):
    schema = _schema_file(tmp_path)
    manifest = tmp_path / "app.yaml"
    manifest.write_text(
        "deployment:\n  mode: deployed\n  tenant:\n    model: Ghost\n    owner_field: ownerId\n"
        "persistence:\n  path: postgresql://db/app\n",
        encoding="utf-8",
    )
    res = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--app-manifest", str(manifest)],
    )
    assert res.exit_code != 0
    assert "is not a model" in res.output
