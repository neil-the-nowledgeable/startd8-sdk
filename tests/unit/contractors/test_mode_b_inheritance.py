"""RUN-009 Gap B — Mode-B inheritance of pre-existing on-disk anchors (TS exports)."""

from __future__ import annotations

from types import SimpleNamespace

from startd8.contractors.prime_contractor import PrimeContractorWorkflow

_collect = PrimeContractorWorkflow._collect_upstream_interfaces
_mirrors = PrimeContractorWorkflow._feature_mirrors_data_model


def _stub(anchors, project_root):
    # bind the staticmethod the FR-3 branch calls (real workflow has it on the class)
    return SimpleNamespace(
        seed_upstream_anchors=anchors, project_root=str(project_root), queue=None,
        _feature_mirrors_data_model=_mirrors,
    )


def _feature(**kw):
    kw.setdefault("dependencies", [])
    kw.setdefault("target_files", [])
    kw.setdefault("description", "")
    kw.setdefault("name", "X")
    return SimpleNamespace(**kw)


class TestModeB:
    def test_anchor_on_disk_is_inherited(self, tmp_path):
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "db.ts").write_text("export const db = {};\n")
        out = _collect(_stub(["lib/db.ts"], tmp_path), _feature(name="ProofPoint API"))
        assert "lib/db.ts" in out and "db" in out and "import EXACTLY" in out

    def test_absent_anchor_skipped(self, tmp_path):
        # declared anchor not on disk → not fabricated into the TS interface render
        out = _collect(_stub(["lib/db.ts"], tmp_path), _feature())
        assert "import EXACTLY" not in out  # no TS interface block produced

    def test_no_anchors_no_effect(self, tmp_path):
        assert _collect(_stub([], tmp_path), _feature()) == ""

    def test_non_ts_anchor_ignored_for_interface_render(self, tmp_path):
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("model A { id String @id }\n")
        # a UI feature (not a data-model mirror) → no TS interface render, no Prisma injection
        out = _collect(_stub(["prisma/schema.prisma"], tmp_path), _feature(target_files=["app/p.tsx"]))
        assert out == ""
