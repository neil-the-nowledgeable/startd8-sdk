"""P2 wiring — PhaseEmitter._emit_manifests writes the artifact family + linkage (FR-WPI-1/7).

Drives the shipped emitter method directly (it only touches output_dir + the extraction
package); the full ingestion run needs an LLM for PARSE and is exercised elsewhere."""

from __future__ import annotations

import json
from pathlib import Path

from startd8.workflows.builtin.plan_ingestion_emitter import PhaseEmitter
from startd8.workflows.builtin.plan_ingestion_models import (
    ComplexityScore,
    ContractorRoute,
    PlanIngestionConfig,
)

KICKOFF = (
    Path(__file__).resolve().parents[2] / "fixtures" / "manifest_extraction" / "kickoff.md"
)


def _emitter(output_dir: Path) -> PhaseEmitter:
    return PhaseEmitter(
        workflow=None,  # _emit_manifests never touches the workflow back-reference
        cfg=PlanIngestionConfig(),
        parsed_plan=None,
        complexity=ComplexityScore(),
        route=ContractorRoute.PRIME,
        output_dir=output_dir,
        doc_path=KICKOFF,
    )


def test_emit_manifests_writes_family_and_returns_linkage(tmp_path: Path) -> None:
    out = tmp_path / "run"
    out.mkdir()
    linkage = _emitter(out)._emit_manifests(
        {"kickoff.md": KICKOFF.read_text(encoding="utf-8")}, project_root=None
    )
    assert (out / "manifests" / "pages.yaml").is_file()
    assert (out / "manifests" / "views.yaml").is_file()
    report = json.loads((out / "manifest-extraction-report.json").read_text(encoding="utf-8"))
    assert report["source_docs"]["kickoff.md"]
    assert (out / "manifest-extraction-report.md").is_file()
    # FR-WPI-7 linkage entries for the seed's artifacts section:
    assert set(linkage) == {
        "manifests_dir", "manifest_sha256s", "extraction_report_path",
        "extraction_report_sha256",
    }
    assert len(linkage["manifest_sha256s"]) == 6


def test_emit_manifests_diff_mode_with_project_root(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / "prisma").mkdir(parents=True)
    (project / "prisma" / "schema.prisma").write_text(
        "model Profile {\n  id String @id\n  name String\n}\n", encoding="utf-8"
    )
    out = tmp_path / "run"
    out.mkdir()
    _emitter(out)._emit_manifests(
        {"kickoff.md": KICKOFF.read_text(encoding="utf-8")}, project_root=project
    )
    report = json.loads((out / "manifest-extraction-report.json").read_text(encoding="utf-8"))
    # Live contract lacks Widget/Tag/WidgetTag — DIFF mode must surface the drift.
    assert any("Widget" in d for d in report["contract_diff"])


def test_emit_manifests_never_blocks_on_failure(tmp_path: Path, monkeypatch) -> None:
    """The seed path is never held hostage: extraction errors return {} and log."""
    out = tmp_path / "run"
    out.mkdir()
    import startd8.manifest_extraction as me

    def boom(*a, **k):
        raise RuntimeError("synthetic extraction failure")

    monkeypatch.setattr(me, "extract_manifests", boom)
    linkage = _emitter(out)._emit_manifests({"kickoff.md": "## Pages\n"}, project_root=None)
    assert linkage == {}
