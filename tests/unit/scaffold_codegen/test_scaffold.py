"""Manifest-driven scaffold generator (class-2 determinism) — REQ-SCAF.

Proves the plumbing emitter is byte-stable, drift-checked against app.yaml, produces a valid
pyproject (the #1 rebuild blocker) and compilable Python, and that the provider recognizes/verifies
its files generically. Non-overlapping with backend_codegen.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from startd8.scaffold_codegen import (
    ScaffoldFileProvider,
    parse_app_manifest,
    render_scaffold,
    scaffold_in_sync,
)
from startd8.contractors.deterministic_providers import ProviderContext

pytestmark = pytest.mark.unit

MANIFEST = """
app:
  name: startdate
  package: app
persistence:
  path: ./data/startd8.db
logging:
  file: ./data/logs/startd8.log
migrations:
  enabled: true
container:
  dockerfile: true
""".strip()


def test_defaults_when_absent():
    m = parse_app_manifest(None)
    assert m.name == "app" and m.package == "app" and m.migrations and m.dockerfile


def test_unknown_key_fails_loud():
    with pytest.raises(ValueError):
        parse_app_manifest("nonsense_key: 1")


def test_render_is_byte_identical_and_full_set():
    a = render_scaffold(MANIFEST)
    assert a == render_scaffold(MANIFEST)
    paths = {rel for rel, _ in a}
    assert paths == {
        "pyproject.toml",
        "app/logging_config.py",
        "Dockerfile",
        "alembic.ini",
        "alembic/env.py",
    }
    for _, content in a:
        assert "# startd8-artifact: scaffold-" in content
        assert "# manifest-sha256:" in content


def test_pyproject_parses_and_has_deps():
    files = dict(render_scaffold(MANIFEST))
    data = tomllib.loads(files["pyproject.toml"])  # tomllib ignores the leading # header lines
    assert data["project"]["name"] == "startdate"
    assert "fastapi" in data["project"]["dependencies"]
    assert "alembic" in data["project"]["optional-dependencies"]["dev"]


def test_drift_in_sync_and_tamper():
    files = dict(render_scaffold(MANIFEST))
    py = files["app/logging_config.py"]
    assert scaffold_in_sync(MANIFEST, py) is True
    assert scaffold_in_sync(MANIFEST, py.replace("INFO", "DEBUG", 1)) is False  # tampered
    assert scaffold_in_sync("app:\n  name: other", py) is False  # stale (manifest changed)


def test_provider_owns_and_verifies(tmp_path):
    files = dict(render_scaffold(MANIFEST))
    (tmp_path / "app.yaml").write_text(MANIFEST, encoding="utf-8")
    ctx = ProviderContext(project_root=tmp_path, source_anchors=("app.yaml",))
    prov = ScaffoldFileProvider()
    py = files["app/logging_config.py"]
    assert prov.owns(tmp_path / "app/logging_config.py", py) is True
    assert prov.is_in_sync(tmp_path / "app/logging_config.py", py, ctx) is True
    assert prov.owns(tmp_path / "x.py", "print('hi')") is False


def test_generated_python_compiles(tmp_path):
    for rel, content in render_scaffold(MANIFEST):
        if not rel.endswith(".py"):
            continue
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
