"""FR-SAP-9 — the domain-preflight Sapper phase (`run_sapper_preflight`)."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from startd8.workflows.builtin.domain_preflight_workflow import (
    SAPPER_PREFLIGHT_ENV,
    run_sapper_preflight,
)

pytestmark = pytest.mark.unit

_HAS_MYPY = shutil.which("mypy") is not None or importlib.util.find_spec("mypy") is not None
requires_mypy = pytest.mark.skipif(not _HAS_MYPY, reason="mypy not available")


def _seed(tmp_path, skeletons):
    seed = {"version": "1", "artifacts": {"skeleton_sources": skeletons}}
    p = tmp_path / "artisan-context-seed.json"
    p.write_text(json.dumps(seed))
    return p


def test_disabled_by_default_returns_none(tmp_path, monkeypatch):
    monkeypatch.delenv(SAPPER_PREFLIGHT_ENV, raising=False)
    seed = _seed(tmp_path, {"app/jobs.py": "x = 1\n"})
    assert run_sapper_preflight(seed, tmp_path) is None  # opt-in: no surprise behavior


def test_enabled_but_no_skeletons_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv(SAPPER_PREFLIGHT_ENV, "1")
    seed = tmp_path / "artisan-context-seed.json"
    seed.write_text(json.dumps({"artifacts": {}}))
    assert run_sapper_preflight(seed, tmp_path) is None


@requires_mypy
def test_enabled_runs_survey_and_writes_report(tmp_path, monkeypatch):
    monkeypatch.setenv(SAPPER_PREFLIGHT_ENV, "true")
    # real ground truth
    proj = tmp_path / "proj"
    (proj / "app").mkdir(parents=True)
    (proj / "app" / "__init__.py").write_text("")
    (proj / "app" / "tables.py").write_text("class JobDescription:\n    id: str = ''\n")
    seed = _seed(
        tmp_path,
        {"app/jobs.py": "from app.tables import JobDescription, Match\ndef f(): ...\n"},
    )

    summary = run_sapper_preflight(seed, proj)
    assert summary is not None
    assert summary["counts"]["refuted"] >= 1          # caught invented Match
    assert summary["blocked"] is False                 # advisory
    assert Path(summary["report_path"]).is_file()      # cross-task report written
    assert (seed.parent / "sapper" / "sapper-friction-report.json").is_file()


def test_survey_error_is_non_fatal(tmp_path, monkeypatch):
    # A bad seed path must not raise — the preflight phase is advisory.
    monkeypatch.setenv(SAPPER_PREFLIGHT_ENV, "1")
    assert run_sapper_preflight(tmp_path / "does-not-exist.json", tmp_path) is None
