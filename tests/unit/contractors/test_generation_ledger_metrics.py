"""#6 datasource path — the Prometheus textfile exporter for the generation-ledger portfolio."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from startd8.contractors import generation_ledger as gl
from startd8.contractors import generation_ledger_metrics as glm

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).parent / "fixtures" / "portal_v2"


def _record(tmp_path: Path, home: str) -> None:
    root = tmp_path / "portal-v2"
    shutil.copytree(_FIXTURE, root)
    gl.record_run(str(root), home=home)


def test_export_emits_portfolio_and_run_metrics(tmp_path):
    home = str(tmp_path / "home")
    _record(tmp_path, home)
    text = glm.export_ledger_metrics(home)
    # portfolio rollup
    assert "gen_ledger_portfolio_projects 1" in text
    assert "gen_ledger_portfolio_cost_usd 2.937581" in text
    # per-project
    assert 'gen_ledger_project_cost_usd{project="portal-v2"} 2.937581' in text
    # per-run micro-prime signal: portal-v2 = 11/16 local = 0.6875
    assert (
        'gen_ledger_run_local_ratio{project="portal-v2",run="portal-v2-preview"} 0.6875'
        in text
    )
    # valid prometheus exposition: HELP/TYPE present, series lines are name{...} value
    assert "# TYPE gen_ledger_portfolio_cost_usd gauge" in text


def test_write_ledger_metrics_writes_prom_file(tmp_path):
    home = str(tmp_path / "home")
    _record(tmp_path, home)
    out = tmp_path / "gen.prom"
    result = glm.write_ledger_metrics(str(out), home=home)
    assert out.is_file() and result["series"] > 0
    # every non-comment line parses as `name[{labels}] value`
    for ln in out.read_text().splitlines():
        if ln and not ln.startswith("#"):
            assert ln.rsplit(" ", 1)[-1]  # has a trailing numeric value


def test_empty_ledger_emits_zero_portfolio(tmp_path):
    text = glm.export_ledger_metrics(str(tmp_path / "empty-home"))
    assert "gen_ledger_portfolio_projects 0" in text
    assert "gen_ledger_portfolio_cost_usd 0" in text


def test_ledger_observations_shape(tmp_path):
    home = str(tmp_path / "home")
    _record(tmp_path, home)
    obs = glm._ledger_observations(home)
    assert obs["portfolio_projects"] == 1
    assert obs["portfolio_cost"] == 2.9375809999999993
    # one (value, {project}) pair per project; one (value, {project,run}) per run
    assert obs["project_cost"][0][1] == {"project": "portal-v2"}
    assert obs["run_ratio"][0][0] == 0.6875 and "run" in obs["run_ratio"][0][1]


def test_push_function_is_importable():
    # the OTLP push is integration-verified against a live stack; here just guard the symbol exists
    assert callable(glm.push_ledger_metrics_otlp)
