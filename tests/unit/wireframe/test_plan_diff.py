"""EC-1 — planned-vs-built diff (`wireframe --diff`): what changed since the last saved preview."""

from __future__ import annotations

import copy
from pathlib import Path

import typer
from typer.testing import CliRunner

from startd8.cli_wireframe import wireframe
from startd8.wireframe import build_wireframe_plan, load_assembly_inputs
from startd8.wireframe.plan_diff import diff_plans, format_diff, load_baseline
from startd8.wireframe.render import plan_body

app = typer.Typer()
app.command()(wireframe)
runner = CliRunner()


def _body(root: Path) -> dict:
    return plan_body(build_wireframe_plan(load_assembly_inputs(project_root=root), authoring=True))


def test_identical_plans_are_unchanged(golden_root: Path) -> None:
    body = _body(golden_root)
    d = diff_plans(body, body)
    assert d["unchanged"] is True and d["fingerprint_changed"] is False
    assert "Nothing changed" in format_diff(d)


def test_diff_detects_added_removed_status_shape_content(golden_root: Path) -> None:
    old = _body(golden_root)
    new = copy.deepcopy(old)
    new["inputs_fingerprint"] = "changed"
    new["shape"]["entities"] = old["shape"]["entities"] + 1                 # shape delta
    new["content_completeness"]["overall"]["authored"] += 1                 # content delta
    sec = new["sections"][0]                                                # per-section item changes
    sec["items"] = list(sec.get("items", [])) + [{"label": "NEW THING", "status": "not_defined"}]
    if sec["items"][:-1]:
        sec["items"][0] = {**sec["items"][0], "status": "invalid"}          # a status flip

    d = diff_plans(old, new)
    assert d["unchanged"] is False and d["fingerprint_changed"] is True
    assert d["shape"]["entities"] == (old["shape"]["entities"], old["shape"]["entities"] + 1)
    assert d["content"] is not None
    sd = next(s for s in d["sections"] if s["key"] == sec["key"])
    assert "NEW THING" in sd["added"]
    report = format_diff(d)
    assert "Shape:" in report and "+ NEW THING" in report


def test_removed_item_is_reported(golden_root: Path) -> None:
    old = _body(golden_root)
    new = copy.deepcopy(old)
    sec = next(s for s in new["sections"] if s.get("items"))
    sec["items"] = list(sec["items"])          # plan_body items are tuples (asdict); JSON round-trips to lists
    dropped = sec["items"].pop(0)["label"]
    d = diff_plans(old, new)
    sd = next(s for s in d["sections"] if s["key"] == sec["key"])
    assert dropped in sd["removed"]


def test_load_baseline_missing_returns_none(tmp_path: Path) -> None:
    assert load_baseline(tmp_path / "nope.json") is None


def test_cli_diff_roundtrip(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    (proj / "prisma").mkdir(parents=True)
    (proj / "prisma" / "schema.prisma").write_text(
        "model Profile {\n  id   String @id @default(cuid())\n  name String\n}\n", encoding="utf-8")
    # 1) no baseline yet → a helpful message, not a crash
    r0 = runner.invoke(app, ["--project", str(proj), "--diff"])
    assert r0.exit_code == 0 and "no saved preview" in r0.output
    # 2) persist a baseline (a normal run writes .startd8/wireframe/wireframe-plan.json)
    assert runner.invoke(app, ["--project", str(proj)]).exit_code == 0
    # 3) diff against it with unchanged inputs → nothing changed
    r2 = runner.invoke(app, ["--project", str(proj), "--diff"])
    assert r2.exit_code == 0 and "Nothing changed" in r2.output
