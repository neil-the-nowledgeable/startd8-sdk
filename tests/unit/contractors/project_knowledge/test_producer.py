"""REQ-CKG-520/521/523 — DraftModeProducer builds the artifact over Phase-1 parsers."""

from __future__ import annotations

from startd8.contractors.project_knowledge import (
    DraftModeProducer,
    ProjectKnowledge,
    ProjectKnowledgeProducer,
)

SCHEMA = (
    "model Capability {\n id String @id @default(cuid())\n name String\n"
    " score Float?\n tags String[]\n outcomes Outcome[]\n}\n"
    "model Outcome {\n id String @id\n label String\n}\n"
)


class TestFieldSetAuthority:
    def test_builds_field_sets_with_types_and_optionality(self):
        pk = DraftModeProducer().build({"prisma/schema.prisma": SCHEMA}, "/proj")
        by_entity = {fs.entity: fs for fs in pk.field_sets}
        assert set(by_entity) == {"Capability", "Outcome"}
        cap = {f.name: f for f in by_entity["Capability"].fields}
        # scalar fields only — the Outcome[] relation is excluded
        assert set(cap) == {"id", "name", "score", "tags"}
        assert cap["score"].optional is True
        assert cap["tags"].is_list is True
        assert cap["name"].type == "String"
        assert by_entity["Capability"].source_file == "prisma/schema.prisma"

    def test_prefers_in_batch_schema_over_disk(self, tmp_path):
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("model OnDisk { id String @id }\n")
        pk = DraftModeProducer().build({"schema.prisma": SCHEMA}, str(tmp_path))
        assert "OnDisk" not in pk.entities()
        assert "Capability" in pk.entities()

    def test_reads_schema_from_disk_when_absent_from_sources(self, tmp_path):
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text(SCHEMA)
        pk = DraftModeProducer().build({}, str(tmp_path))
        assert "Capability" in pk.entities()


class TestOmissions:
    def test_no_schema_states_omission_not_empty_authority(self, tmp_path):
        pk = DraftModeProducer().build({"app/page.tsx": "export const x = 1"}, str(tmp_path))
        assert pk.field_sets == ()
        assert pk.has_field_authority is False
        assert any("do not assume a field set" in o for o in pk.omissions)


class TestConvergence:
    def test_satisfies_producer_protocol(self):
        assert isinstance(DraftModeProducer(), ProjectKnowledgeProducer)

    def test_build_uses_phase1_prisma_parser(self, monkeypatch):
        import startd8.contractors.project_knowledge.producer as prod
        called = {}
        real = prod.parse_prisma_schema

        def _spy(text):
            called["hit"] = True
            return real(text)

        monkeypatch.setattr(prod, "parse_prisma_schema", _spy)
        DraftModeProducer().build({"schema.prisma": SCHEMA}, "/proj")
        assert called.get("hit") is True  # no bespoke scanner — reuses §11 resolver

    def test_build_returns_project_knowledge(self):
        out = DraftModeProducer().build({}, "/proj")
        assert isinstance(out, ProjectKnowledge)
        assert out.project_root == "/proj"
