# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""FR-9 wiring on the --prometheus path of compare-live: fail-loud guards + convergence."""
from __future__ import annotations

import json
from pathlib import Path

from startd8.observability.compare_live import run_live_comparison


def _run(**kw):
    # read_fr_coverage_fn stubbed → no manifest needed; we exercise the Path-1 workload branch only.
    return run_live_comparison(
        manifest=Path("x"), prometheus="http://prom", warm_up="workload",
        read_fr_coverage_fn=lambda p: {}, workload_sleep_fn=lambda s: None,
        workload_settle_attempts=2, **kw,
    )


def _blob(report) -> str:
    return json.dumps(report.to_dict()) if hasattr(report, "to_dict") else str(report.__dict__)


def test_workload_requires_spec():
    assert "requires --workload-spec" in _blob(_run())


def test_workload_requires_subject_url():
    # spec given but no ingress → fail-loud before loading the file
    assert "requires --subject-url" in _blob(_run(workload_spec=Path("s.json")))


def test_workload_non_convergence_is_unknown(tmp_path):
    spec = tmp_path / "w.json"
    spec.write_text(json.dumps({
        "name": "t", "auth": {"kind": "none"},
        "steps": [{"name": "hit", "kind": "http", "method": "GET", "path": "/x",
                   "registers_metric": "m_total"}],
    }))
    # drive it, but make the metric never land → the run must be unknown (no fidelity), not green.
    # (uses the real engine; the http step will just fail to connect to http://ingress → not exercised)
    r = _run(workload_spec=spec, subject_url="http://ingress.invalid")
    b = _blob(r)
    assert "workload" in b and "did not converge" in b
