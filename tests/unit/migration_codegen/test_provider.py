"""Migration provider + drift re-render tests (Tier-1 PR2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.contractors.deterministic_providers import ProviderContext
from startd8.migration_codegen import (
    MigrationFileProvider,
    migration_revision_in_sync,
    next_revision,
    plan_migration,
    rerender_revision,
)
from startd8.migration_codegen.check import pending_migration_message

pytestmark = pytest.mark.unit

_SCHEMA_V1 = (
    "model Item {\n"
    "  id String @id @default(cuid())\n"
    "  title String\n"
    "}\n"
)


def test_rerender_baseline_revision(tmp_path: Path):
    versions = tmp_path / "versions"
    versions.mkdir()
    result = next_revision(versions, _SCHEMA_V1, "baseline")
    assert result is not None
    fname, text, _ = result
    path = versions / fname
    path.write_text(text, encoding="utf-8")
    assert rerender_revision(path, versions) == text
    assert migration_revision_in_sync(path, text, versions)


def test_tampered_revision_not_in_sync(tmp_path: Path):
    versions = tmp_path / "versions"
    versions.mkdir()
    result = next_revision(versions, _SCHEMA_V1, "baseline")
    assert result is not None
    fname, text, _ = result
    path = versions / fname
    path.write_text(text + "\n# tamper", encoding="utf-8")
    assert not migration_revision_in_sync(path, path.read_text(), versions)


def test_provider_owns_and_syncs(tmp_path: Path):
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    result = next_revision(versions, _SCHEMA_V1, "baseline")
    assert result is not None
    fname, text, _ = result
    path = versions / fname
    path.write_text(text, encoding="utf-8")
    provider = MigrationFileProvider()
    ctx = ProviderContext(project_root=tmp_path, source_anchors=("prisma/schema.prisma",))
    assert provider.owns(path, text)
    assert provider.is_in_sync(path, text, ctx)


def test_pending_message_when_schema_grows(tmp_path: Path):
    versions = tmp_path / "versions"
    versions.mkdir()
    v1 = next_revision(versions, _SCHEMA_V1, "baseline")
    assert v1 is not None
    (versions / v1[0]).write_text(v1[1], encoding="utf-8")
    v2_schema = _SCHEMA_V1 + 'model Tag {\n  id String @id @default(cuid())\n  label String\n}\n'
    msg = pending_migration_message(versions, v2_schema)
    assert msg is not None
    assert "migration pending" in msg
    assert plan_migration(v2_schema, _SCHEMA_V1).upgrade_ops
