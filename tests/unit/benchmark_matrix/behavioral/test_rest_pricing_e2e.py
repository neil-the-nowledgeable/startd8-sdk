"""Full-sandbox e2e for the REST pricing lane: a real Python server launched as a SUBPROCESS by the
harness, http-readiness-probed, and scored over loopback — the complete path a model-generated cell
takes (provision -> sandbox launch -> http readiness -> run_rest_pricing_suite).

The fixture is a CORRECT stdlib server (the oracle), so a passing harness yields functional == 1.0.
Unlike test_rest_pricing_suite (in-process), this exercises the subprocess + http readiness mode +
provisioning path. Skips if the seed isn't present.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from startd8.benchmark_matrix.behavioral.execute import run_behavioral_cell

_REPO = Path(__file__).resolve().parents[4]
_SEED = _REPO / "docs/design/model-benchmark/seeds/seed-rest-pricingservice.json"
_FIXTURE = Path(__file__).parent / "fixtures" / "rest_pricing_server.py"

pytestmark = pytest.mark.skipif(not _SEED.is_file(), reason="rest pricing seed not present")


def test_rest_server_scores_full_coverage_via_subprocess(tmp_path):
    seed = json.loads(_SEED.read_text())
    target_files = seed["tasks"][0]["config"]["context"]["target_files"]
    dst = tmp_path / target_files[0]
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FIXTURE, dst)

    res = run_behavioral_cell(seed, tmp_path, "rest-pricingservice", target_files)

    assert res.has_suite
    assert not res.degraded, json.dumps(res.provenance, indent=2)
    suite = res.provenance.get("suite", {})
    failing = [r for r in suite.get("results", []) if not r.get("passed")]
    assert res.functional == 1.0, f"functional={res.functional}; failing={failing}"
