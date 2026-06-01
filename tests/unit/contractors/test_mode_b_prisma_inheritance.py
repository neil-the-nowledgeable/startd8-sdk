"""RUN-009 Gap B FR-3/FR-4 — Prisma field-set inheritance + absent-anchor warning."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.contractors.upstream_interface import render_prisma_field_sets

_collect = PrimeContractorWorkflow._collect_upstream_interfaces
_mirrors = PrimeContractorWorkflow._feature_mirrors_data_model

PRISMA = (
    "model Profile {\n  id String @id @default(cuid())\n  summary String?\n  yearsExp Int?\n}\n"
)


class TestRenderPrismaFieldSets:
    def test_renders_real_field_names(self):
        out = render_prisma_field_sets(PRISMA)
        assert "Profile" in out and "summary: String?" in out and "yearsExp: Int?" in out
        assert "bio:" not in out  # no rendered field named bio
        assert "mirror these field names" in out.lower()

    def test_empty_when_no_models(self):
        assert render_prisma_field_sets("// just a comment\n") == ""


class TestFeatureTargeting:
    def test_mirror_features_detected(self):
        assert _mirrors(SimpleNamespace(target_files=["lib/value-model.ts"], description="")) is True
        assert _mirrors(SimpleNamespace(target_files=["lib/schemas.ts"], description="")) is True
        assert _mirrors(SimpleNamespace(target_files=[], description="Zod schema mirroring Prisma")) is True

    def test_non_mirror_features_skipped(self):
        assert _mirrors(SimpleNamespace(target_files=["app/page.tsx"], description="UI page")) is False


class TestPrismaInheritanceWiring:
    def _stub(self, tmp_path, anchors):
        s = SimpleNamespace(seed_upstream_anchors=anchors, project_root=str(tmp_path), queue=None)
        s._feature_mirrors_data_model = _mirrors  # staticmethod → plain fn
        return s

    def test_prisma_injected_for_mirror_feature(self, tmp_path):
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text(PRISMA)
        stub = self._stub(tmp_path, ["prisma/schema.prisma"])
        feature = SimpleNamespace(dependencies=[], name="Zod", target_files=["lib/value-model.ts"], description="")
        out = _collect(stub, feature)
        assert "summary: String?" in out and "yearsExp: Int?" in out

    def test_prisma_not_injected_for_ui_feature(self, tmp_path):
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text(PRISMA)
        stub = self._stub(tmp_path, ["prisma/schema.prisma"])
        feature = SimpleNamespace(dependencies=[], name="UI", target_files=["app/page.tsx"], description="UI")
        assert _collect(stub, feature) == ""

    def test_absent_anchor_warns(self, tmp_path, caplog):
        stub = self._stub(tmp_path, ["lib/db.ts"])  # not on disk
        feature = SimpleNamespace(dependencies=[], name="X", target_files=[], description="")
        with caplog.at_level(logging.WARNING):
            _collect(stub, feature)
        assert any("FR-4" in r.message and "lib/db.ts" in r.message for r in caplog.records)
