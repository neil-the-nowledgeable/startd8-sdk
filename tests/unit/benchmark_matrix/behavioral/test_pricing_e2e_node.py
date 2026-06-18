"""End-to-end harness proof for the pricing seed (gated): a REAL Node PricingService, launched by
the Track 2 behavioral harness under the sandbox, scored over loopback.

Unlike test_pricing_suite.py (which validates the suite against an in-process Python oracle), this
exercises the full path the benchmark uses: prepare_node_workdir (node_modules + pricing.proto
provisioning, FR-14), resolve_serve_command (startup contract, FR-10), run_service_sandboxed
(loopback-allowed / egress-denied, setsid+killpg teardown), then run_pricing_suite over the wire.

Gated: needs ``node`` on PATH and the vendored runtime (``node_runtime/vendor.sh``). Skips otherwise.
The fixture server is a CORRECT implementation (the oracle), so a passing harness yields functional
== 1.0; anything less is a harness defect, not a model defect.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from startd8.benchmark_matrix.behavioral import execute
from startd8.benchmark_matrix.behavioral.execute import run_behavioral_cell

_REPO = Path(__file__).resolve().parents[4]
_SEED = _REPO / "docs/design/model-benchmark/seeds/seed-pricingservice.json"
_FIXTURE = Path(__file__).parent / "fixtures" / "reference_pricing_server.js"

pytestmark = [
    pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH"),
    pytest.mark.skipif(not (execute._NODE_RUNTIME / "node_modules").is_dir(),
                       reason="node runtime not vendored — run node_runtime/vendor.sh"),
]


def test_reference_node_server_scores_full_coverage(tmp_path):
    seed = json.loads(_SEED.read_text())
    target_files = seed["tasks"][0]["config"]["context"]["target_files"]

    server_path = tmp_path / target_files[0]
    server_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FIXTURE, server_path)

    res = run_behavioral_cell(seed, tmp_path, "pricingservice", target_files)

    assert res.has_suite
    assert not res.degraded, f"harness degraded: {json.dumps(res.provenance, indent=2)}"
    suite = res.provenance.get("suite", {})
    failing = [r for r in suite.get("results", []) if not r.get("passed")]
    assert res.functional == 1.0, f"functional={res.functional}; failing={failing}"
    assert res.provenance.get("network_isolated") is True  # FR-T2-SEC: egress denied, loopback allowed
