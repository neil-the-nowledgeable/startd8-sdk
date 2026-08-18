"""REQ-prime-project-generation-ledger — I5 (FR-4 CLI) + I4 (FR-6 verify) surface pins."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.contractors import generation_ledger as gl
from startd8.contractors.cli_prime_ledger import prime_ledger_app

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).parent / "fixtures" / "portal_v2"
_RUNNER = CliRunner()


def _record_portal_v2(tmp_path: Path, home: str, *, complete: bool = False) -> Path:
    root = tmp_path / "portal-v2"
    shutil.copytree(_FIXTURE, root)
    if complete:
        for rel in [
            ".startd8/prime-postmortem-report.json",
            ".startd8/prime-postmortem-summary.md",
            ".startd8/kaizen-metrics.json",
            ".startd8/forward-manifest.json",
            ".cap-dev-pipe/pipeline-output/portal-v2-preview/run-provenance.json",
            ".cap-dev-pipe/pipeline-output/portal-v2-preview/portal-v2-preview-artifact-manifest.yaml",
            ".cap-dev-pipe/pipeline-output/portal-v2-preview/project-context.yaml",
        ]:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{}", encoding="utf-8")
    gl.record_run(str(root), home=home)
    return root


# ── FR-4: list / show / artifacts ──────────────────────────────────────────────────────────────────


def test_list_json_lists_recorded_projects(tmp_path):
    home = str(tmp_path / "home")
    _record_portal_v2(tmp_path, home)
    res = _RUNNER.invoke(prime_ledger_app, ["list", "--json", "--home", home])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    ids = [p["project_id"] for p in payload["projects"]]
    assert "portal-v2" in ids


def test_list_empty_is_clean_exit(tmp_path):
    res = _RUNNER.invoke(prime_ledger_app, ["list", "--home", str(tmp_path / "empty")])
    assert res.exit_code == 0
    assert "no projects recorded" in res.stdout


def test_show_json_returns_the_run(tmp_path):
    home = str(tmp_path / "home")
    _record_portal_v2(tmp_path, home)
    res = _RUNNER.invoke(
        prime_ledger_app, ["show", "portal-v2", "--json", "--home", home]
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    run = data["batches"][0]["runs"][0]
    assert run["run_id"] == "portal-v2-preview"
    assert run["cost_usd"] == 2.9375809999999993


def test_show_unknown_project_errors(tmp_path):
    res = _RUNNER.invoke(
        prime_ledger_app, ["show", "ghost", "--home", str(tmp_path / "home")]
    )
    assert res.exit_code == 2


def test_artifacts_prints_the_map(tmp_path):
    home = str(tmp_path / "home")
    _record_portal_v2(tmp_path, home)
    res = _RUNNER.invoke(
        prime_ledger_app,
        ["artifacts", "portal-v2", "portal-v2-preview", "--json", "--home", home],
    )
    assert res.exit_code == 0
    artifacts = json.loads(res.stdout)
    non_null = {k: v for k, v in artifacts.items() if v is not None}
    assert len(non_null) == 10 and "generation_manifest" in non_null


# ── FR-6: verify (advisory exit codes) ───────────────────────────────────────────────────────────────


def test_verify_clean_exits_zero(tmp_path):
    home = str(tmp_path / "home")
    _record_portal_v2(tmp_path, home, complete=True)
    res = _RUNNER.invoke(prime_ledger_app, ["verify", "portal-v2", "--home", home])
    assert res.exit_code == 0 and "clean" in res.stdout


def test_verify_phantom_exits_one(tmp_path):
    home = str(tmp_path / "home")
    root = _record_portal_v2(tmp_path, home, complete=True)
    (root / ".startd8" / "forward-manifest.json").unlink()
    res = _RUNNER.invoke(
        prime_ledger_app, ["verify", "portal-v2", "--json", "--home", home]
    )
    assert res.exit_code == 1
    findings = json.loads(res.stdout)
    assert any(f["kind"] == "PHANTOM" for f in findings)
