"""Standalone-runner tests: ingestion-seed loader + `startd8 sapper survey` CLI."""

from __future__ import annotations

import importlib.util
import json
import shutil

import pytest
from typer.testing import CliRunner

from startd8.sapper.host import load_from_ingestion_seed

pytestmark = pytest.mark.unit

_HAS_MYPY = shutil.which("mypy") is not None or importlib.util.find_spec("mypy") is not None
requires_mypy = pytest.mark.skipif(not _HAS_MYPY, reason="mypy not available")


def _write_seed(tmp_path, skeletons):
    seed = {"version": "1", "artifacts": {"skeleton_sources": skeletons}}
    p = tmp_path / "artisan-context-seed.json"
    p.write_text(json.dumps(seed))
    return p


def test_loader_reads_skeletons_and_builds_minimal_manifest(tmp_path):
    seed = _write_seed(tmp_path, {"app/jobs.py": "from app.tables import Match\ndef f(): ...\n"})
    manifest, skeletons = load_from_ingestion_seed(str(seed))
    assert skeletons == {"app/jobs.py": "from app.tables import Match\ndef f(): ...\n"}
    # minimal manifest reconstructed from skeleton paths (full manifest not persisted by EMIT yet)
    assert "app/jobs.py" in manifest.file_specs


def test_loader_reconstructs_full_manifest_when_persisted(tmp_path):
    # Sapper 3a: EMIT now persists `forward_manifest` → the loader rebuilds the real manifest,
    # so cross-contract + per-element lenses light up (not just the minimal fallback).
    from startd8.forward_manifest import (
        ForwardFileSpec,
        ForwardImportSpec,
        ForwardManifest,
    )

    fm = ForwardManifest(
        file_specs={
            "app/jobs.py": ForwardFileSpec(
                file="app/jobs.py",
                imports=[ForwardImportSpec(kind="from", module="app.tables", names=["Match"])],
            )
        }
    )
    seed = {
        "artifacts": {
            "skeleton_sources": {"app/jobs.py": "from app.tables import Match\ndef f(): ...\n"},
            "forward_manifest": fm.model_dump(),
        }
    }
    p = tmp_path / "artisan-context-seed.json"
    p.write_text(json.dumps(seed))

    manifest, _ = load_from_ingestion_seed(str(p))
    # real manifest reconstructed: the import claim is present (not an empty minimal spec)
    assert manifest.file_specs["app/jobs.py"].imports
    assert manifest.file_specs["app/jobs.py"].imports[0].module == "app.tables"


def test_loader_accepts_directory(tmp_path):
    _write_seed(tmp_path, {"a.py": "x = 1\n"})
    manifest, skeletons = load_from_ingestion_seed(str(tmp_path))
    assert "a.py" in skeletons


def test_loader_missing_or_empty_returns_none(tmp_path):
    assert load_from_ingestion_seed(str(tmp_path / "nope.json")) == (None, {})
    empty = tmp_path / "artisan-context-seed.json"
    empty.write_text(json.dumps({"artifacts": {}}))
    assert load_from_ingestion_seed(str(empty)) == (None, {})


def test_loader_malformed_json_is_guarded_not_raised(tmp_path):
    # A corrupt seed must degrade to (None, {}) — never a traceback into the CLI.
    bad = tmp_path / "artisan-context-seed.json"
    bad.write_text("{ not valid json :::")
    assert load_from_ingestion_seed(str(bad)) == (None, {})
    # A JSON value that isn't an object is also handled.
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2, 3]")
    assert load_from_ingestion_seed(str(arr)) == (None, {})


@requires_mypy
def test_cli_survey_end_to_end(tmp_path):
    # Real ground truth: app.tables has JobDescription, not Match.
    proj = tmp_path / "proj"
    (proj / "app").mkdir(parents=True)
    (proj / "app" / "__init__.py").write_text("")
    (proj / "app" / "tables.py").write_text("class JobDescription:\n    id: str = ''\n")
    seed = _write_seed(
        tmp_path,
        {"app/jobs.py": "from app.tables import JobDescription, Match\nfrom flask import Blueprint\ndef f(): ...\n"},
    )

    # Invoke through the mounted group (the real `startd8 sapper survey` path).
    from startd8.cli import app

    res = CliRunner().invoke(
        app,
        ["sapper", "survey", "--from", str(seed), "--project-root", str(proj), "--out", str(tmp_path / "out")],
    )
    assert res.exit_code == 0, res.output
    assert "Sapper survey" in res.output
    # the survey caught the invented Match (existence) and flask (convention)
    assert "Match" in res.output and "flask" in res.output
    assert (tmp_path / "out" / "sapper-friction-report.json").is_file()
