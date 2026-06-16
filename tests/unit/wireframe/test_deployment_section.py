"""A8 — `startd8 wireframe` surfaces the deployment mode + posture + coherence (FR-CFG-6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.wireframe import Status, build_wireframe_plan, load_assembly_inputs

pytestmark = pytest.mark.unit


def _plan(tmp_path: Path, app_yaml: str):
    p = tmp_path / "app.yaml"
    p.write_text(app_yaml, encoding="utf-8")
    return build_wireframe_plan(load_assembly_inputs(overrides={"app": p}, project_root=tmp_path))


def _details(section):
    return {i.label: i.detail for i in section.items}


def test_deployment_section_deployed_posture(tmp_path):
    plan = _plan(
        tmp_path, "deployment:\n  mode: deployed\npersistence:\n  path: postgresql://db/app\n"
    )
    sec = plan.section("deployment")
    assert sec is not None and sec.title == "Deployment mode" and sec.status == Status.PLANNED
    d = _details(sec)
    assert d["mode"] == "deployed"
    assert "0.0.0.0" in d["bind"]
    assert "shared DB" in d["persistence"] and "migrations" in d["schema-init"]


def test_deployment_section_installed_default(tmp_path):
    plan = _plan(tmp_path, "app:\n  name: d\n")  # no deployment block -> installed
    d = _details(plan.section("deployment"))
    assert d["mode"] == "installed"
    assert "127.0.0.1" in d["bind"]
    assert "SQLite" in d["persistence"]


def test_deployment_section_surfaces_coherence_error(tmp_path):
    # deployed + the default SQLite persistence -> coherence ERROR (advisory in wireframe).
    sec = _plan(tmp_path, "deployment:\n  mode: deployed\n").section("deployment")
    assert sec.status == Status.INVALID
    labels = [i.label for i in sec.items]
    assert "coherence:deployed-sqlite-file" in labels
    assert sec.consequence  # non-empty: explains generate backend will refuse
