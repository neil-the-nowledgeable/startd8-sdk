# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""FR-28 — latest-run resolution for `fde explain`."""

from __future__ import annotations

import json

import pytest

from startd8.fde.sources import LatestRunError, resolve_latest_run


def _make_run(base, project, run_name, *, triage=False, prime_result=False):
    d = (
        base
        / ".cap-dev-pipe"
        / "pipeline-output"
        / project
        / run_name
        / "plan-ingestion"
    )
    d.mkdir(parents=True, exist_ok=True)
    if triage:
        (d / "service-assistant-triage.json").write_text(
            json.dumps({"run": {"run_id": run_name}, "verdict": {}})
        )
    if prime_result:
        (d / "prime-result.json").write_text(json.dumps({"history": []}))
    return d


def test_picks_newest_run_with_triage(tmp_path):
    _make_run(tmp_path, "proj", "run-001-20260101T0000", triage=True)
    newest = _make_run(tmp_path, "proj", "run-038-20260604T1332", triage=True)
    _make_run(tmp_path, "proj", "run-020-20260602T2131", triage=True)
    resolved = resolve_latest_run(project_root=tmp_path)
    assert resolved == newest


def test_falls_back_to_newest_with_prime_result_when_no_triage(tmp_path):
    _make_run(tmp_path, "proj", "run-001-20260101T0000", prime_result=True)
    newest_pr = _make_run(tmp_path, "proj", "run-009-20260109T0000", prime_result=True)
    resolved = resolve_latest_run(project_root=tmp_path)
    assert resolved == newest_pr


def test_prefers_triage_over_a_newer_run_without_one(tmp_path):
    with_triage = _make_run(tmp_path, "proj", "run-005-20260105T0000", triage=True)
    # A newer run that only has a prime-result must NOT win over an older triaged run.
    _make_run(tmp_path, "proj", "run-040-20260640T0000", prime_result=True)
    assert resolve_latest_run(project_root=tmp_path) == with_triage


def test_multi_project_requires_disambiguation(tmp_path):
    _make_run(tmp_path, "proj-a", "run-001-20260101T0000", triage=True)
    _make_run(tmp_path, "proj-b", "run-001-20260101T0000", triage=True)
    with pytest.raises(LatestRunError) as exc:
        resolve_latest_run(project_root=tmp_path)
    assert "multiple projects" in str(exc.value)


def test_project_id_disambiguates(tmp_path):
    _make_run(tmp_path, "proj-a", "run-001-20260101T0000", triage=True)
    want = _make_run(tmp_path, "proj-b", "run-002-20260102T0000", triage=True)
    assert resolve_latest_run(project_root=tmp_path, project_id="proj-b") == want


def test_no_base_raises(tmp_path):
    with pytest.raises(LatestRunError) as exc:
        resolve_latest_run(project_root=tmp_path)
    assert "no pipeline-output base" in str(exc.value)


def test_no_run_with_artifacts_raises(tmp_path):
    # A project dir with an empty run (no triage, no prime-result) → actionable error.
    (
        tmp_path
        / ".cap-dev-pipe"
        / "pipeline-output"
        / "proj"
        / "run-001-x"
        / "plan-ingestion"
    ).mkdir(parents=True)
    with pytest.raises(LatestRunError):
        resolve_latest_run(project_root=tmp_path)
