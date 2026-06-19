"""Full-sandbox e2e for the GraphQL pricing lane: a real graphql-core server launched as a SUBPROCESS,
with graphql-core installed from the cell's requirements.txt into .pydeps and made importable via the
harness PYTHONPATH injection, http-readiness-probed, and scored over loopback.

This is the e2e that VALIDATES the .pydeps-import fix (execute.py) — the REST lane (stdlib) never
needed it. Gated behind STARTD8_RUN_INTEGRATION=1 because provisioning pip-installs graphql-core
(network). The fixture is a correct server (oracle) → a passing harness yields functional == 1.0.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from startd8.benchmark_matrix.behavioral.execute import run_behavioral_cell

_REPO = Path(__file__).resolve().parents[4]
_SEED = _REPO / "docs/design/model-benchmark/seeds/seed-graphql-pricingservice.json"
_FIXTURE = Path(__file__).parent / "fixtures" / "graphql_pricing_server.py"

pytestmark = pytest.mark.skipif(
    os.environ.get("STARTD8_RUN_INTEGRATION") != "1" or not _SEED.is_file(),
    reason="graphql e2e installs graphql-core (network); set STARTD8_RUN_INTEGRATION=1",
)


def test_graphql_server_scores_full_coverage_via_subprocess(tmp_path):
    seed = json.loads(_SEED.read_text())
    target_files = seed["tasks"][0]["config"]["context"]["target_files"]
    dst = tmp_path / target_files[0]
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FIXTURE, dst)
    (dst.parent / "requirements.txt").write_text("graphql-core>=3.2\n")  # provisioned into .pydeps

    res = run_behavioral_cell(seed, tmp_path, "graphql-pricingservice", target_files)

    assert res.has_suite
    assert not res.degraded, json.dumps(res.provenance, indent=2)
    failing = [r for r in res.provenance.get("suite", {}).get("results", []) if not r.get("passed")]
    assert res.functional == 1.0, f"functional={res.functional}; failing={failing}"
