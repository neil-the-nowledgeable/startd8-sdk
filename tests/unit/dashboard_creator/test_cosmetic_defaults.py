"""Compiled-JSON golden checks for the Phase-0b cosmetic defaults (AES-014/020/040/041).

These assert on the *evaluated* dashboard JSON (post-Jsonnet-compile), not the generated
.libsonnet source — so they verify the mixin constructor defaults as Grafana sees them.
They require a working Jsonnet toolchain + vendored mixin deps; when that is unavailable
(e.g. CI without `gojsonnet`/`jb install`) they **skip with a reason**, never silently pass
(NFR-AES-5 / R2-F5).
"""

import asyncio
import inspect

import pytest

from startd8.dashboard_creator import DashboardCreatorWorkflow

_DS_VAR = {"type": "prometheusDatasource", "name": "datasource", "label": "DS"}


def _compile(spec, tmp_path):
    """Run the real workflow (generate -> jsonnet compile -> validate). Skip if the
    Jsonnet toolchain / vendored mixin is unavailable; fail on any other error."""
    result = DashboardCreatorWorkflow().run({"spec": spec, "output_dir": str(tmp_path)})
    if inspect.isawaitable(result):
        result = asyncio.get_event_loop().run_until_complete(result)
    if not result.success:
        err = (getattr(result, "error", "") or "").lower()
        if any(t in err for t in ("jsonnet", "vendor", "mixin", "jb install", "toolchain")):
            pytest.skip(f"Jsonnet toolchain/mixin unavailable: {result.error}")
        pytest.fail(f"workflow failed: {result.error}")
    import json
    from pathlib import Path
    return json.load(open(Path(result.output["json_path"])))


def _panels(dash):
    return {p["title"]: p for p in dash["panels"]}


class TestCosmeticDefaults:
    def test_piechart_donut_legend_bottom_percent(self, tmp_path):
        spec = {"title": "pie", "uid": "cc-test-pie", "variables": [_DS_VAR],
                "panels": [{"type": "piechart", "title": "P", "targets": [{"expr": "up"}]}]}
        p = _panels(_compile(spec, tmp_path))["P"]
        assert p["options"]["pieType"] == "donut"               # AES-014
        assert p["options"]["legend"]["placement"] == "bottom"
        assert p["options"]["displayLabels"] == ["percent"]

    def test_gauge_bargauge_base_step_only(self, tmp_path):
        spec = {"title": "g", "uid": "cc-test-g", "variables": [_DS_VAR],
                "panels": [{"type": "gauge", "title": "G", "expr": "up"},
                           {"type": "barGauge", "title": "BG", "expr": "up"}]}
        P = _panels(_compile(spec, tmp_path))
        # AES-020: no arbitrary 80/100 or 60/80 ramp — a single base step.
        for name in ("G", "BG"):
            steps = P[name]["fieldConfig"]["defaults"]["thresholds"]["steps"]
            assert [s["color"] for s in steps] == ["green"]
            assert steps[0]["value"] is None

    def test_refresh_off_by_default(self, tmp_path):
        spec = {"title": "r", "uid": "cc-test-r", "variables": [_DS_VAR],
                "panels": [{"type": "stat", "title": "S", "expr": "up"}]}
        assert _compile(spec, tmp_path).get("refresh") in ("", None)  # AES-040

    def test_graphtooltip_shared_crosshair_for_multi_timeseries(self, tmp_path):
        spec = {"title": "ts", "uid": "cc-test-ts", "variables": [_DS_VAR],
                "panels": [{"type": "timeseries", "title": "A", "targets": [{"expr": "up"}]},
                           {"type": "timeseries", "title": "B", "targets": [{"expr": "up"}]}]}
        assert _compile(spec, tmp_path).get("graphTooltip") == 1   # AES-041

    def test_graphtooltip_default_for_single_timeseries(self, tmp_path):
        spec = {"title": "ts1", "uid": "cc-test-ts1", "variables": [_DS_VAR],
                "panels": [{"type": "timeseries", "title": "A", "targets": [{"expr": "up"}]},
                           {"type": "stat", "title": "S", "expr": "up"}]}
        assert _compile(spec, tmp_path).get("graphTooltip") == 0   # < 2 timeseries
