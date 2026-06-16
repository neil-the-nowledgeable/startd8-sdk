"""--from-run mode tests (FR-WPI-6/7): both cap-dev-pipe layouts, fallbacks, linkage."""

from __future__ import annotations

import json
from pathlib import Path


from startd8.manifest_extraction import extract_manifests, report_to_json
from startd8.wireframe import Status, build_wireframe_plan, load_assembly_inputs
from startd8.wireframe.render import delivery_inventory, plan_to_json, run_linkage

KICKOFF = (
    Path(__file__).resolve().parents[2] / "fixtures" / "manifest_extraction" / "kickoff.md"
)

LIVE_SCHEMA = (
    "model Profile {\n  id String @id\n  name String\n  bio String?\n}\n"
    "model Widget {\n  id String @id\n  title String\n  score Int?\n  profileId String\n}\n"
    "model Tag {\n  id String @id\n  label String\n}\n"
    "model WidgetTag {\n  widgetId String\n  tagId String\n  @@id([widgetId, tagId])\n}\n"
)


def _make_run(run_dir: Path) -> None:
    """Simulate the EMIT artifact family: manifests/ + report (the shipped shapes)."""
    result = extract_manifests({"kickoff.md": KICKOFF.read_text(encoding="utf-8")})
    (run_dir / "manifests").mkdir(parents=True)
    for fname, text in result.manifests.items():
        (run_dir / "manifests" / fname).write_text(text, encoding="utf-8")
    (run_dir / "manifest-extraction-report.json").write_text(
        report_to_json(result), encoding="utf-8"
    )
    (run_dir / "prime-context-seed.json").write_text('{"version": "1.0.0"}', encoding="utf-8")


def _make_project(project: Path) -> None:
    (project / "prisma").mkdir(parents=True)
    (project / "prisma" / "schema.prisma").write_text(LIVE_SCHEMA, encoding="utf-8")


def test_from_run_embedded_layout(tmp_path: Path) -> None:
    """Run dir INSIDE the project (the embedded cap-dev-pipe layout)."""
    project = tmp_path / "proj"
    _make_project(project)
    run_dir = project / ".cap-dev-pipe" / "pipeline-output" / "run-001"
    _make_run(run_dir)

    inputs = load_assembly_inputs(project_root=project, from_run=run_dir)
    # Emitted manifests resolve from the run; the live contract stays on convention (DIFF mode).
    assert inputs.entry("pages").source == "run"
    assert inputs.entry("views").source == "run"
    assert inputs.entry("schema").source == "convention"

    plan = build_wireframe_plan(inputs)
    assert plan.section("pages").status == Status.PLANNED
    assert plan.section("views").status == Status.PLANNED
    assert plan.readiness["views"] == "ready"
    assert plan.input_provenance["pages"]["source"] == "run"


def test_from_run_canonical_layout_outside_project(tmp_path: Path) -> None:
    """Run dir OUTSIDE the project (canonical cap-dev-pipe) — the sweep-2 second-root case."""
    project = tmp_path / "proj"
    _make_project(project)
    run_dir = tmp_path / "cap-dev-pipe" / "pipeline-output" / "run-002"  # NOT under project
    _make_run(run_dir)

    inputs = load_assembly_inputs(project_root=project, from_run=run_dir)
    assert inputs.entry("pages").source == "run"
    plan = build_wireframe_plan(inputs)
    assert plan.section("pages").status == Status.PLANNED


def test_flags_still_beat_run_manifests(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _make_project(project)
    run_dir = project / "run"
    _make_run(run_dir)
    override = project / "prisma" / "other-pages.yaml"
    override.write_text("pages:\n  - {slug: /, title: X, content: pages/x.md}\n", encoding="utf-8")
    inputs = load_assembly_inputs(
        project_root=project, from_run=run_dir, overrides={"pages": override}
    )
    assert inputs.entry("pages").source == "flag"


def test_run_linkage_block(tmp_path: Path) -> None:
    """FR-WPI-7: prose → extraction → manifest → wireframe, without reading the seed body."""
    project = tmp_path / "proj"
    _make_project(project)
    run_dir = project / "run"
    _make_run(run_dir)

    linkage = run_linkage(run_dir)
    assert linkage is not None
    assert "kickoff.md" in linkage["source_doc_checksums"]
    assert set(linkage["manifest_sha256s"]) == {
        "ai_passes.yaml", "app.yaml", "completeness.yaml",
        "human_inputs.yaml", "pages.yaml", "views.yaml",
    }
    assert len(linkage["seed_sha256"]) == 64
    assert len(linkage["extraction_report_sha256"]) == 64

    plan = build_wireframe_plan(load_assembly_inputs(project_root=project, from_run=run_dir))
    body = json.loads(plan_to_json(plan, linkage=linkage))
    assert body["run_linkage"]["run_dir"] == str(run_dir)


def test_run_linkage_none_without_report(tmp_path: Path) -> None:
    assert run_linkage(tmp_path) is None


def test_delivery_inventory_iterations(tmp_path: Path) -> None:
    """FR-WPI-9: static section→iteration mapping; AI items land in iteration ③."""
    project = tmp_path / "proj"
    _make_project(project)
    run_dir = project / "run"
    _make_run(run_dir)
    plan = build_wireframe_plan(load_assembly_inputs(project_root=project, from_run=run_dir))

    inventory = delivery_inventory(plan)
    assert [g["iteration"] for g in inventory] == [1, 2, 3]
    it1 = {i["section"] for i in inventory[0]["items"]}
    it2 = {i["section"] for i in inventory[1]["items"]}
    it3_labels = [i["label"] for i in inventory[2]["items"]]
    assert it1 <= {"scaffold", "services", "entities", "deployment"}
    assert it2 <= {"forms", "pages", "views", "completeness"}
    assert any(label.startswith("AI pass:") for label in it3_labels)  # AI items → ③
    # And it appears in the JSON contract.
    body = json.loads(plan_to_json(plan))
    assert len(body["delivery_inventory"]) == 3
