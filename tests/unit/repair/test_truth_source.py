"""Unit tests for the name-repair TruthSource (Inc 1, FR-2/FR-10)."""

from __future__ import annotations

import pytest

from startd8.repair.truth_source import (
    ArtifactTruthSource,
    LiveDiskTruthSource,
    TruthSource,
)

_SCHEMA = """
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model Capability {
  id          String  @id @default(cuid())
  ownerId     String  @default("local")
  name        String?
  category    String?
  description String?
  proficiency String?
  notes       String?
  outcomes    CapabilityOutcome[]
}

model Metric {
  id          String  @id @default(cuid())
  name        String?
  value       String?
  unit        String?
  direction   String?
  timeframe   String?
  description String?
  notes       String?
}
"""


@pytest.fixture
def project(tmp_path):
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(_SCHEMA, encoding="utf-8")
    lib = tmp_path / "lib"
    (lib / "ai").mkdir(parents=True)
    (lib / "db.ts").write_text("export const db = {}\n", encoding="utf-8")
    (lib / "logger.ts").write_text("export const logger = {}\n", encoding="utf-8")
    (lib / "ai" / "service.ts").write_text("export const aiService = {}\n", encoding="utf-8")
    (lib / "value-model.ts").write_text("export const valueModel = {}\n", encoding="utf-8")
    return tmp_path


def test_live_truth_source_satisfies_protocol(project):
    assert isinstance(LiveDiskTruthSource(project), TruthSource)


def test_prisma_fields_are_the_real_set_no_inventions(project):
    ts = LiveDiskTruthSource(project)
    cap = ts.prisma_fields("Capability")
    assert "name" in cap and "category" in cap and "description" in cap
    # The run-011 inventions must NOT be present.
    assert "aiRefId" not in cap
    assert "label" not in cap
    # Metric has no FK to Outcome — outcomeId is not a field.
    assert "outcomeId" not in ts.prisma_fields("Metric")


def test_prisma_fields_unknown_model_is_empty(project):
    assert LiveDiskTruthSource(project).prisma_fields("DoesNotExist") == frozenset()


def test_module_paths_seeds_known_inventions(project):
    paths = LiveDiskTruthSource(project).module_paths()
    assert paths["@/lib/prisma"] == "@/lib/db"
    assert paths["@/lib/ai/client"] == "@/lib/ai/service"


def test_resolvable_specifiers_enumerate_on_disk_lib(project):
    specs = LiveDiskTruthSource(project).resolvable_specifiers()
    assert "@/lib/db" in specs
    assert "@/lib/logger" in specs
    assert "@/lib/ai/service" in specs
    assert "@/lib/value-model" in specs
    # An invented path is NOT in the resolvable set.
    assert "@/lib/prisma" not in specs


def test_src_lib_layout_also_enumerated(tmp_path):
    (tmp_path / "src" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "lib" / "db.ts").write_text("export const db = {}\n", encoding="utf-8")
    specs = LiveDiskTruthSource(tmp_path).resolvable_specifiers()
    assert "@/lib/db" in specs


def test_index_file_contributes_directory_form(tmp_path):
    (tmp_path / "lib" / "ai").mkdir(parents=True)
    (tmp_path / "lib" / "ai" / "index.ts").write_text("export const x = 1\n", encoding="utf-8")
    specs = LiveDiskTruthSource(tmp_path).resolvable_specifiers()
    assert "@/lib/ai" in specs


def test_missing_schema_degrades_to_empty_no_raise(tmp_path):
    ts = LiveDiskTruthSource(tmp_path)  # no prisma/, no lib/
    assert ts.prisma_fields("Capability") == frozenset()
    assert ts.resolvable_specifiers() == frozenset()


def test_artifact_truth_source_is_a_documented_stub(tmp_path):
    ats = ArtifactTruthSource(tmp_path / "forward_project_knowledge.json")
    with pytest.raises(NotImplementedError):
        ats.prisma_fields("Capability")
    with pytest.raises(NotImplementedError):
        ats.module_paths()
    with pytest.raises(NotImplementedError):
        ats.resolvable_specifiers()
