"""RUN-009 Gap B — Mode-B inheritance of pre-existing on-disk anchors.

Verifies _collect_upstream_interfaces feeds pre-existing upstream anchors (Gap A's
upstream_anchors signal) into the design context, so a consumer inherits the real
module path (@/lib/db) instead of inventing one (@/lib/prisma). Uses a stub bound
to the method to avoid constructing the full workflow.
"""

from __future__ import annotations

from types import SimpleNamespace

from startd8.contractors.prime_contractor import PrimeContractorWorkflow

_collect = PrimeContractorWorkflow._collect_upstream_interfaces


class TestModeB:
    def test_anchor_on_disk_is_inherited(self, tmp_path):
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "db.ts").write_text("export const db = {};\n")
        stub = SimpleNamespace(
            seed_upstream_anchors=["lib/db.ts"], project_root=str(tmp_path), queue=None,
        )
        feature = SimpleNamespace(dependencies=[], name="ProofPoint API")
        out = _collect(stub, feature)
        assert "lib/db.ts" in out          # the real module path is surfaced
        assert "db" in out                 # its real export
        assert "import EXACTLY" in out     # the grounding instruction

    def test_absent_anchor_skipped(self, tmp_path):
        # declared anchor not on disk (e.g. wiped pre-Gap-A) → not fabricated
        stub = SimpleNamespace(
            seed_upstream_anchors=["lib/db.ts"], project_root=str(tmp_path), queue=None,
        )
        feature = SimpleNamespace(dependencies=[], name="X")
        assert _collect(stub, feature) == ""

    def test_no_anchors_no_effect(self, tmp_path):
        stub = SimpleNamespace(seed_upstream_anchors=[], project_root=str(tmp_path), queue=None)
        feature = SimpleNamespace(dependencies=[], name="X")
        assert _collect(stub, feature) == ""

    def test_non_ts_anchor_ignored(self, tmp_path):
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("model A { id String @id }\n")
        stub = SimpleNamespace(
            seed_upstream_anchors=["prisma/schema.prisma"], project_root=str(tmp_path), queue=None,
        )
        feature = SimpleNamespace(dependencies=[], name="X")
        # .prisma is not a TS/JS import target for this renderer (FR-3 handles Prisma separately)
        assert _collect(stub, feature) == ""
