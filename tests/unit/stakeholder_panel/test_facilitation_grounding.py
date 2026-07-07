# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Grounding must surface a BUILT application, not just the schema.

Regression for "the reviewers think nothing is built": the kernel survey only reports
models/docs/fixtures, so a generated FastAPI app grounded to the panel as "a schema, nothing built
yet". These pin that ``_scan_built_app`` / ``_gather_artifact`` now report routers, auth, an
entrypoint, and tests when they exist on disk.
"""

from __future__ import annotations

from startd8.stakeholder_panel.facilitation import (
    _gather_artifact,
    _render_built_app,
    _scan_built_app,
)


def _make_app(root):
    app = root / "app"
    app.mkdir()
    (app / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {}\n"
    )
    (app / "routers.py").write_text(
        "from fastapi import APIRouter\nr = APIRouter()\n\n@r.post('/items')\ndef create():\n    return {}\n"
    )
    (app / "portal_auth.py").write_text("def get_principal():\n    return None\n")
    (app / "models.py").write_text("class M:\n    pass\n")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_smoke.py").write_text("def test_ok():\n    assert True\n")


def test_scan_built_app_detects_routes_auth_entrypoint_tests(tmp_path):
    _make_app(tmp_path)
    app = _scan_built_app(tmp_path)
    assert app["py_modules"] >= 5
    assert app["endpoints"] >= 2  # @app.get + @r.post + APIRouter(
    assert any("main.py" in e for e in app["entrypoints"])
    assert any("auth" in a for a in app["auth_modules"])
    assert app["test_files"] == 1
    assert any("main.py" in rf or "routers.py" in rf for rf in app["route_files"])


def test_scan_skips_virtualenv_and_caches(tmp_path):
    _make_app(tmp_path)
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    for i in range(5):
        (venv / f"junk{i}.py").write_text("@app.get('/x')\ndef x():\n    return {}\n")
    app = _scan_built_app(tmp_path)
    # the 5 venv modules (and their fake routes) must not inflate the counts
    assert app["py_modules"] < 10
    assert not any(".venv" in rf for rf in app["route_files"])


def test_gather_artifact_surfaces_built_app(tmp_path):
    _make_app(tmp_path)
    artifact, warning = _gather_artifact(tmp_path)
    assert "Built application (already exists" in artifact
    assert "route/endpoint files" in artifact
    assert warning == ""  # survey read fine; no degrade


def test_render_built_app_empty_is_honest(tmp_path):
    # a schema-only project (no app code) must say so, not fabricate a running system
    out = _render_built_app(_scan_built_app(tmp_path))
    assert "No application code found" in out
